import asyncio
import logging
import random
import re
import time
import uuid
from dataclasses import asdict, dataclass, replace
from typing import Any, Awaitable, Callable, Union, cast

from .bingo import (
    CATEGORY_POOL,
    PRESET_BEGINNER,
    best_erase,
    best_mark_cell,
    bingo_off_by,
    bot_answer,
    closest_year_winners,
    evaluate_answer,
    generate_card,
    has_bingo,
)
from .catalog import (
    EXTRA_TRACK_PREFIX,
    Catalog,
    Track,
    itunes_lookup_track,
    remember_community_track,
)
from .persistence import PERSIST_VERSION
from .stats import (
    PlayerResult,
    record_activity,
    record_game_result,
    record_placement,
)
from .schemas import (
    AudioMode,
    AudioModeChanged,
    AvatarChanged,
    BingoAnswered,
    BingoAnswering,
    BingoGameStarted,
    BingoMarksChanged,
    BingoPlayerResult,
    BingoRoundDone,
    BingoRoundResult,
    BingoSettingsChanged,
    BingoSpin,
    CardsAdjusted,
    CardSnapshot,
    CardTargetChanged,
    CategoryFilterChanged,
    ConnectionChanged,
    ExtraTrackSummary,
    ExtraTracksTotalChanged,
    GameMode,
    GameModeChanged,
    GameOver,
    HitsterGameStarted,
    HitsterTurnChanged,
    HostChanged,
    OnlyPlayerAddedChanged,
    PlacementResult,
    PlacingPhase,
    PlayerJoined,
    PlayerKicked,
    PlayerLeft,
    Player,
    PromoState,
    RematchStarted,
    RoomSnapshot,
    RoomState,
    RoundSettingsChanged,
    StealAttempted,
    StealEnabledChanged,
    StealStarted,
)

log = logging.getLogger(__name__)

# defaults for the host-tunable round timers (used when the host hasn't
# overridden them; the room reads these via properties so tests can still
# monkeypatch the module constant for fast timing)
SNIPPET_DURATION_S = 15
PLACING_TIMEOUT_S = 30
STEAL_TIMEOUT_S = 12  # window for others to race-steal a missed card
HITSTER_INTRO_DURATION_S = 4
MIN_SNIPPET_S = 5
MAX_SNIPPET_S = 30
MIN_PLACING_S = 5
MAX_PLACING_S = 60
MIN_STEAL_S = 5
MAX_STEAL_S = 30
DEFAULT_CARD_TARGET = 10
MIN_CARD_TARGET = 2
MAX_CARD_TARGET = 30
DEFAULT_SONGS_PER_PLAYER = 10
MIN_SONGS_PER_PLAYER = 0
MAX_SONGS_PER_PLAYER = 20
DEFAULT_STARTING_CARDS = 1
MIN_STARTING_CARDS = 1
MAX_STARTING_CARDS = 5
MAX_PLAYERS = 8  # humans + bots
# bingo mode timings — the answer window is host-tunable, the rest is pacing
BINGO_ANSWER_S = 25
MIN_BINGO_ANSWER_S = 10
MAX_BINGO_ANSWER_S = 60
BINGO_SPIN_S = 3.5  # disco-ball wheel animation before the song starts
BINGO_MARK_S = 15  # window for correct players to mark (then auto-pick)
BINGO_LINGER_S = 5.0  # pause on the resolved reveal before the next spin
BINGO_MIN_POOL = 10  # a bingo needs >= 5 correct answers in a line
# rounds auto-advance, so an abandoned-but-still-connected room would churn
# through the whole pool on its own — after this many consecutive rounds
# without a single answer the game ends itself (marks decide, rematch revives)
BINGO_IDLE_ROUNDS = 3
# AI opponents (singleplayer): the bot knows the true year, so difficulty is just
# how often it plays the correct gap (else it drops a plausible neighbour).
BOT_THINK_S = 2.0
BOT_HIT_PROB = {"easy": 0.5, "medium": 0.72, "hard": 0.9}
BOT_NAMES = [
    "Ada", "Turing", "Vega", "Nova", "Echo", "Pixel",
    "Disco", "Groove", "Riff", "Bassy", "Melody", "Tempo",
]
# anti-clustering: how many recently-played tracks a room remembers across
# rematches and avoids re-picking while fresher songs remain
RECENT_MEMORY = 80
# states whose logical room state is safe to snapshot to disk (no timer is
# mid-flight that the snapshot would have to encode); the manager persists on
# every broadcast in these states and restores on boot — see persistence.py
CHECKPOINT_STATES: frozenset[RoomState] = frozenset(
    {"lobby", "hitster_reveal", "bingo_reveal", "game_over"}
)

# avatar identifiers are client-defined ("style:seed" / "img:file") but pass
# through the server to everyone — keep them short and boring
_AVATAR_RE = re.compile(r"^[a-z0-9-]{1,24}:[A-Za-z0-9._-]{1,48}$")


def _clean_avatar(avatar: str) -> str:
    return avatar if _AVATAR_RE.fullmatch(avatar) else ""


@dataclass(frozen=True, slots=True)
class ContributedTrack:
    track: Track
    added_by_id: str
    added_by_name: str


BroadcastMessage = Union[
    AvatarChanged,
    BingoAnswered,
    BingoAnswering,
    BingoGameStarted,
    BingoMarksChanged,
    BingoRoundDone,
    BingoRoundResult,
    BingoSettingsChanged,
    BingoSpin,
    GameModeChanged,
    PlayerJoined,
    PlayerLeft,
    PlayerKicked,
    CardsAdjusted,
    ConnectionChanged,
    HostChanged,
    PlacingPhase,
    AudioModeChanged,
    StealEnabledChanged,
    StealStarted,
    StealAttempted,
    CategoryFilterChanged,
    OnlyPlayerAddedChanged,
    ExtraTracksTotalChanged,
    CardTargetChanged,
    HitsterGameStarted,
    HitsterTurnChanged,
    PlacementResult,
    GameOver,
    RematchStarted,
    RoundSettingsChanged,
    PromoState,
]
Broadcaster = Callable[[BroadcastMessage], Awaitable[None]]
OnEmpty = Callable[[], Awaitable[None]]


class RoomError(Exception):
    pass


class Room:
    def __init__(
        self,
        code: str,
        catalog: Catalog,
        broadcast: Broadcaster,
        on_empty: OnEmpty,
    ) -> None:
        self.code = code
        self._catalog = catalog
        self._broadcast = broadcast
        self._on_empty = on_empty

        self.players: list[Player] = []
        self.state: RoomState = "lobby"
        self.cumulative_scores: dict[str, int] = {}
        # AI opponents: player_id -> difficulty level (also marks who is a bot)
        self.bot_difficulty: dict[str, str] = {}
        self._bot_steal_tasks: list[asyncio.Task[None]] = []
        # per-game counters for the persistent stats (player_id -> counters);
        # written to SQLite once when the game finishes
        self.player_stats: dict[str, dict[str, int]] = {}
        # players currently disconnected mid-game: kept in the roster (shown as
        # "offline") and skipped in the rotation; cleared when they reconnect
        self.disconnected: set[str] = set()

        # settings
        self.category_filter: list[str] = list(catalog.available_categories())
        self.only_player_added: bool = False
        # "online" (every device plays) | "couch" (only the host's device plays)
        self.audio_mode: AudioMode = "online"
        # on a wrong placement, others race to steal the card (host-toggleable)
        self.steal_enabled: bool = True
        # host-tunable round timers — None means "use the module default" (so
        # tests can still monkeypatch the constant); set by the host setters
        self._snippet_override: int | None = None
        self._placing_override: int | None = None
        self._steal_override: int | None = None
        self.starting_cards: int = DEFAULT_STARTING_CARDS
        # which rules the next game uses + the bingo knobs (host-set)
        self.game_mode: GameMode = "classic"
        self.bingo_categories: list[str] = list(PRESET_BEGINNER)
        self._bingo_answer_override: int | None = None
        self.extra_tracks: dict[str, ContributedTrack] = {}
        self.card_target: int = DEFAULT_CARD_TARGET
        # max songs each player may contribute; host-configurable, independent
        # of the card target
        self.songs_per_player: int = DEFAULT_SONGS_PER_PLAYER

        # game state
        self.hands: dict[str, list[CardSnapshot]] = {}
        self.turn_order: list[str] = []
        self.turn_index: int = 0
        # players who reached the card target, in finish order (= final ranking)
        self.finished_players: list[str] = []

        # current turn state
        self.current_track: Track | None = None
        self.current_track_added_by_id: str | None = None
        self.current_track_added_by_name: str | None = None
        self.last_placement_result: PlacementResult | None = None
        self.played_track_ids: set[str] = set()
        # recently-played track ids across rematches (anti-clustering); NOT reset
        # on rematch/abort — only grows and is capped at RECENT_MEMORY
        self.recent_track_ids: list[str] = []

        self._snippet_task: asyncio.Task[None] | None = None
        self._placing_task: asyncio.Task[None] | None = None
        self._intro_task: asyncio.Task[None] | None = None
        self._placing_deadline_ms: int | None = None

        # steal phase ("open race" after a wrong placement)
        self._steal_task: asyncio.Task[None] | None = None
        self._steal_deadline_ms: int | None = None
        self._steal_placer_id: str | None = None  # who missed
        self._steal_attempted: set[str] = set()  # stealers already out (wrong)
        self._steal_winner_id: str | None = None
        # carried from the active placement into the (possibly deferred) reveal
        self._active_slot_index: int | None = None
        self._active_correct: bool = False
        self._active_finished_place: int | None = None
        self._steal_finished_place: int | None = None

        # bingo game state (turn_order doubles as the participants list; the
        # rotation index is unused — everyone plays every round)
        self.bingo_cards: dict[str, list[int]] = {}  # player -> 25 colour slots
        self.bingo_marks: dict[str, set[int]] = {}  # player -> marked cells
        self.bingo_round: int = 0
        self.bingo_winners: list[str] = []
        self._bingo_idle_rounds: int = 0  # consecutive rounds with no answers
        self.last_bingo_result: BingoRoundResult | None = None
        self._bingo_category_idx: int | None = None  # 0..4 into bingo_categories
        # the previous round's song — the Zeitduell (vs_prev) pivot; public
        # info (it was just revealed), None in round 1
        self._bingo_prev_title: str | None = None
        self._bingo_prev_year: int | None = None
        self._bingo_answers: dict[str, str] = {}  # raw answers this round
        self._bingo_deadline_ms: int | None = None  # answering OR marking
        self._bingo_mark_pending: set[str] = set()
        self._bingo_erase_pending: set[str] = set()
        self._bingo_task: asyncio.Task[None] | None = None
        self._bot_bingo_tasks: list[asyncio.Task[None]] = []

        # easter egg: owner-triggered fake-ads overlay shown to everyone but
        # the person who toggled it
        self.promo_active: bool = False
        self.promo_by: str | None = None

    # ---------- queries ----------

    @property
    def host_id(self) -> str | None:
        # the host is the first *connected human* (bots never host; host powers
        # migrate when the host drops and return on reconnect)
        for p in self.players:
            if not p.is_bot and p.id not in self.disconnected:
                return p.id
        for p in self.players:
            if not p.is_bot:
                return p.id
        return None

    def _is_bot(self, player_id: str) -> bool:
        return player_id in self.bot_difficulty

    def _human_players(self) -> list[Player]:
        return [p for p in self.players if not p.is_bot]

    def _connected_humans(self) -> list[Player]:
        return [p for p in self._human_players() if p.id not in self.disconnected]

    def _is_singleplayer(self) -> bool:
        # one human playing against bots — used to drop multiplayer-only UI/limits
        return len(self._human_players()) == 1 and any(
            p.is_bot for p in self.players
        )

    @property
    def per_player_cap(self) -> int:
        return self.songs_per_player

    @property
    def snippet_duration_s(self) -> int:
        return (
            SNIPPET_DURATION_S
            if self._snippet_override is None
            else self._snippet_override
        )

    @property
    def placing_seconds(self) -> int:
        return (
            PLACING_TIMEOUT_S
            if self._placing_override is None
            else self._placing_override
        )

    @property
    def steal_seconds(self) -> int:
        return (
            STEAL_TIMEOUT_S
            if self._steal_override is None
            else self._steal_override
        )

    @property
    def bingo_answer_seconds(self) -> int:
        return (
            BINGO_ANSWER_S
            if self._bingo_answer_override is None
            else self._bingo_answer_override
        )

    @property
    def current_turn_player_id(self) -> str | None:
        if not self.turn_order:
            return None
        if self.turn_index >= len(self.turn_order):
            return None
        return self.turn_order[self.turn_index]

    def has_player(self, player_id: str) -> bool:
        return any(p.id == player_id for p in self.players)

    def is_active_turn_player(self, player_id: str) -> bool:
        """True when this player is the one currently on the clock (their snippet
        is playing or they're placing) — i.e. their leaving stalls the table, so
        the disconnect is resolved immediately instead of after the grace."""
        return (
            self.state in ("hitster_listening", "hitster_placing")
            and self.current_turn_player_id == player_id
        )

    def _eligible_pool_size(self) -> int:
        categories_set = set(self.category_filter)
        count = 0
        if not self.only_player_added:
            for t in self._catalog.tracks:
                if t.category in categories_set:
                    count += 1
        for c in self.extra_tracks.values():
            if c.track.category in categories_set:
                count += 1
        return count

    def _podium_places(self) -> int:
        """How many podium places are played for, by game-start player count.

        2 players -> 1st only, 3 players -> 1st+2nd, 4+ -> 1st+2nd+3rd.
        """
        n = len(self.turn_order)
        if n >= 4:
            return 3
        if n == 3:
            return 2
        return 1

    def _podium_complete(self) -> bool:
        if not self.turn_order or not self.finished_players:
            return False
        if len(self.finished_players) >= self._podium_places():
            return True
        # fewer than 2 contenders left (others finished or left) — nothing
        # meaningful remains to play for
        active_unfinished = [
            pid
            for pid in self.turn_order
            if pid not in self.finished_players and self.has_player(pid)
        ]
        return len(active_unfinished) <= 1

    def _your_extra_tracks(self, player_id: str) -> list[ExtraTrackSummary]:
        return [
            ExtraTrackSummary(
                track_id=c.track.id.removeprefix(EXTRA_TRACK_PREFIX),
                title=c.track.title,
                artist=c.track.artist,
                category=c.track.category,
                preview_url=c.track.preview_url,
            )
            for c in self.extra_tracks.values()
            if c.added_by_id == player_id
        ]

    def snapshot_for(self, player_id: str) -> RoomSnapshot:
        in_round = self.state in (
            "hitster_listening",
            "hitster_placing",
            "bingo_answering",
        )
        stealing = self.state == "hitster_stealing"
        return RoomSnapshot(
            state=self.state,
            players=list(self.players),
            host_id=self.host_id,
            cumulative_scores=dict(self.cumulative_scores),
            disconnected=sorted(self.disconnected),
            category_filter=list(self.category_filter),
            available_categories=self._catalog.available_categories(),
            category_counts=self._catalog.category_counts(),
            extra_tracks_total=len(self.extra_tracks),
            per_player_cap=self.per_player_cap,
            effective_pool_size=self._eligible_pool_size(),
            your_extra_tracks=self._your_extra_tracks(player_id),
            only_player_added=self.only_player_added,
            card_target=self.card_target,
            audio_mode=self.audio_mode,
            steal_enabled=self.steal_enabled,
            snippet_duration_s=int(self.snippet_duration_s),
            placing_seconds=int(self.placing_seconds),
            steal_seconds=int(self.steal_seconds),
            starting_cards=self.starting_cards,
            hands={pid: list(cards) for pid, cards in self.hands.items()},
            turn_order=list(self.turn_order),
            finished_players=list(self.finished_players),
            current_turn_player_id=self.current_turn_player_id,
            current_preview_url=(
                self.current_track.preview_url
                if in_round and self.current_track is not None
                else None
            ),
            placing_deadline_ms=(
                self._placing_deadline_ms
                if self.state == "hitster_placing"
                else None
            ),
            steal_placer_id=self._steal_placer_id if stealing else None,
            steal_deadline_ms=self._steal_deadline_ms if stealing else None,
            steal_attempted=sorted(self._steal_attempted) if stealing else [],
            last_placement_result=(
                self.last_placement_result
                if self.state == "hitster_reveal"
                else None
            ),
            game_mode=self.game_mode,
            bingo_categories=list(self.bingo_categories),
            bingo_answer_seconds=int(self.bingo_answer_seconds),
            bingo_cards={
                pid: list(card) for pid, card in self.bingo_cards.items()
            },
            bingo_marks={
                pid: sorted(marks) for pid, marks in self.bingo_marks.items()
            },
            bingo_round=self.bingo_round,
            bingo_category_index=self._bingo_category_idx,
            bingo_prev_title=self._bingo_prev_title,
            bingo_prev_year=self._bingo_prev_year,
            bingo_deadline_ms=self._bingo_deadline_ms,
            bingo_answered=(
                sorted(self._bingo_answers)
                if self.state == "bingo_answering"
                else []
            ),
            bingo_mark_pending=sorted(self._bingo_mark_pending),
            bingo_erase_pending=sorted(self._bingo_erase_pending),
            last_bingo_result=(
                self.last_bingo_result
                if self.state == "bingo_reveal"
                else None
            ),
            bingo_winners=list(self.bingo_winners),
            promo_active=self.promo_active,
            promo_by=self.promo_by,
        )

    # ---------- checkpoint persistence (see persistence.py) ----------

    def to_persist(self) -> dict[str, Any]:
        """JSON-able snapshot of the logical room state.

        Only meaningful in CHECKPOINT_STATES (the manager only calls it
        there). Timers, socket state, the current mystery track and the promo
        easter egg are deliberately not part of it.
        """
        return {
            "version": PERSIST_VERSION,
            "saved_at": int(time.time()),
            "code": self.code,
            "state": self.state,
            "players": [p.model_dump() for p in self.players],
            "bot_difficulty": dict(self.bot_difficulty),
            "cumulative_scores": dict(self.cumulative_scores),
            "player_stats": {
                pid: dict(st) for pid, st in self.player_stats.items()
            },
            "category_filter": list(self.category_filter),
            "only_player_added": self.only_player_added,
            "audio_mode": self.audio_mode,
            "steal_enabled": self.steal_enabled,
            "snippet_override": self._snippet_override,
            "placing_override": self._placing_override,
            "steal_override": self._steal_override,
            "starting_cards": self.starting_cards,
            "card_target": self.card_target,
            "songs_per_player": self.songs_per_player,
            "extra_tracks": [
                {
                    "track": asdict(c.track),
                    "added_by_id": c.added_by_id,
                    "added_by_name": c.added_by_name,
                }
                for c in self.extra_tracks.values()
            ],
            "hands": {
                pid: [c.model_dump() for c in cards]
                for pid, cards in self.hands.items()
            },
            "turn_order": list(self.turn_order),
            "turn_index": self.turn_index,
            "finished_players": list(self.finished_players),
            "played_track_ids": sorted(self.played_track_ids),
            "recent_track_ids": list(self.recent_track_ids),
            "last_placement_result": (
                self.last_placement_result.model_dump()
                if self.last_placement_result is not None
                else None
            ),
            # bingo mode — settings always, game state only mid-bingo-game.
            # Pending marks/erases are deliberately NOT persisted: a restored
            # reveal comes back resolved-as-is (at most one round's marks are
            # lost, same deal as classic losing the interrupted turn).
            "game_mode": self.game_mode,
            "bingo_categories": list(self.bingo_categories),
            "bingo_answer_override": self._bingo_answer_override,
            "bingo_round": self.bingo_round,
            "bingo_cards": {
                pid: list(card) for pid, card in self.bingo_cards.items()
            },
            "bingo_marks": {
                pid: sorted(marks) for pid, marks in self.bingo_marks.items()
            },
            "bingo_category_idx": self._bingo_category_idx,
            "last_bingo_result": (
                self.last_bingo_result.model_dump()
                if self.last_bingo_result is not None
                else None
            ),
        }

    @classmethod
    def from_persist(
        cls,
        data: dict[str, Any],
        catalog: Catalog,
        broadcast: Broadcaster,
        on_empty: OnEmpty,
    ) -> "Room":
        """Rebuild a room from a checkpoint snapshot.

        Restored rooms start with no running timers and every human marked
        offline — players resume through the normal reconnect path. A lobby
        snapshot (including the pre-intro save of a game that never reached
        its first reveal) comes back as a *clean* lobby: settings, bots and
        contributed songs survive; game state and human roster entries don't
        (humans re-add themselves on rejoin, keeping their player_id, so their
        contributions stay theirs).
        """
        state = data["state"]
        if state not in CHECKPOINT_STATES:
            raise ValueError(f"not a checkpoint state: {state}")
        room = cls(
            code=str(data["code"]),
            catalog=catalog,
            broadcast=broadcast,
            on_empty=on_empty,
        )
        players = [Player.model_validate(p) for p in data["players"]]
        room.bot_difficulty = {
            str(k): str(v) for k, v in data["bot_difficulty"].items()
        }
        room.category_filter = [str(c) for c in data["category_filter"]]
        room.only_player_added = bool(data["only_player_added"])
        room.audio_mode = (
            "couch" if data["audio_mode"] == "couch" else "online"
        )
        room.steal_enabled = bool(data["steal_enabled"])
        snip = data["snippet_override"]
        room._snippet_override = int(snip) if snip is not None else None
        plac = data["placing_override"]
        room._placing_override = int(plac) if plac is not None else None
        steal = data["steal_override"]
        room._steal_override = int(steal) if steal is not None else None
        room.starting_cards = int(data["starting_cards"])
        room.card_target = int(data["card_target"])
        room.songs_per_player = int(data["songs_per_player"])
        for entry in data["extra_tracks"]:
            track = Track(**entry["track"])
            room.extra_tracks[track.id] = ContributedTrack(
                track=track,
                added_by_id=str(entry["added_by_id"]),
                added_by_name=str(entry["added_by_name"]),
            )
        room.recent_track_ids = [str(t) for t in data["recent_track_ids"]]
        # bingo settings (`.get` — snapshots predating bingo restore fine)
        room.game_mode = (
            "bingo" if data.get("game_mode") == "bingo" else "classic"
        )
        cats_raw = data.get("bingo_categories")
        cats = (
            [str(c) for c in cast(list[Any], cats_raw)]
            if isinstance(cats_raw, list)
            else []
        )
        if len(cats) == 5 and all(c in CATEGORY_POOL for c in cats):
            room.bingo_categories = cats
        answer_override = data.get("bingo_answer_override")
        room._bingo_answer_override = (
            int(answer_override) if answer_override is not None else None
        )

        if state == "lobby":
            room.players = [p for p in players if p.is_bot]
            room.cumulative_scores = {p.id: 0 for p in room.players}
            return room

        # mid-game (reveal) or game over: full roster, everyone offline until
        # they reconnect; the existing offline mechanic handles the rest
        room.state = state
        room.players = players
        room.disconnected = {p.id for p in players if not p.is_bot}
        room.cumulative_scores = {
            str(k): int(v) for k, v in data["cumulative_scores"].items()
        }
        room.player_stats = {
            str(pid): {str(k): int(v) for k, v in st.items()}
            for pid, st in data["player_stats"].items()
        }
        room.hands = {
            str(pid): [CardSnapshot.model_validate(c) for c in cards]
            for pid, cards in data["hands"].items()
        }
        room.turn_order = [str(p) for p in data["turn_order"]]
        room.turn_index = int(data["turn_index"])
        room.finished_players = [str(p) for p in data["finished_players"]]
        room.played_track_ids = {str(t) for t in data["played_track_ids"]}
        lpr = data["last_placement_result"]
        if state == "hitster_reveal" and lpr is not None:
            room.last_placement_result = PlacementResult.model_validate(lpr)
        # bingo game state: a restored bingo_reveal sits paused (no timers
        # survive a restart) until the first human reconnects — see add_player
        room.bingo_round = int(data.get("bingo_round", 0))
        cards_raw = cast(dict[str, Any], data.get("bingo_cards") or {})
        room.bingo_cards = {
            str(pid): [int(c) for c in card]
            for pid, card in cards_raw.items()
        }
        marks_raw = cast(dict[str, Any], data.get("bingo_marks") or {})
        room.bingo_marks = {
            str(pid): {int(c) for c in marks}
            for pid, marks in marks_raw.items()
        }
        cat_idx = data.get("bingo_category_idx")
        room._bingo_category_idx = int(cat_idx) if cat_idx is not None else None
        lbr = data.get("last_bingo_result")
        if state == "bingo_reveal" and lbr is not None:
            room.last_bingo_result = BingoRoundResult.model_validate(lbr)
            # the song just revealed is the NEXT round's Zeitduell pivot
            # (current_track itself is deliberately not persisted)
            room._bingo_prev_title = room.last_bingo_result.card.title
            room._bingo_prev_year = room.last_bingo_result.card.year
        return room

    # ---------- player lifecycle ----------

    async def add_player(
        self, name: str, player_id: str | None, avatar: str = ""
    ) -> Player:
        avatar = _clean_avatar(avatar)
        if player_id is not None:
            for p in self.players:
                if p.id == player_id:
                    # the client's stored preference wins on a (re)join
                    if avatar and avatar != p.avatar:
                        p.avatar = avatar
                        await self._broadcast(
                            AvatarChanged(player_id=p.id, avatar=avatar)
                        )
                    # reconnect of an existing player → back online
                    if player_id in self.disconnected:
                        old_host = self.host_id
                        self.disconnected.discard(player_id)
                        await self._broadcast(
                            ConnectionChanged(
                                disconnected=sorted(self.disconnected),
                                host_id=self.host_id,
                            )
                        )
                        if (
                            self.host_id != old_host
                            and self.host_id is not None
                        ):
                            await self._broadcast(
                                HostChanged(host_id=self.host_id)
                            )
                    # a room restored from a checkpoint sits paused on its last
                    # bingo reveal (no timers survive a restart) — the first
                    # human back in the door un-pauses the game
                    if (
                        self.state == "bingo_reveal"
                        and not self._bingo_mark_pending
                        and not self._bingo_erase_pending
                        and (self._bingo_task is None or self._bingo_task.done())
                    ):
                        self._bingo_task = asyncio.create_task(
                            self._bingo_linger_then_next()
                        )
                    return p
        new_id = player_id or uuid.uuid4().hex
        new_player = Player(id=new_id, name=name, avatar=avatar)
        self.players.append(new_player)
        # a reconnecting player keeps their preserved hand → restore their score
        # to match (it may have been dropped while they were gone)
        self.cumulative_scores[new_id] = len(self.hands.get(new_id, []))
        record_activity("player_joined", self.code, {"name": name})
        await self._broadcast(PlayerJoined(player=new_player))
        await self._broadcast_pool_state()
        return new_player

    async def set_avatar(self, player_id: str, avatar: str) -> None:
        """Change your own avatar — allowed in any state (cosmetic only)."""
        cleaned = _clean_avatar(avatar)
        if not cleaned:
            raise RoomError("invalid avatar")
        for p in self.players:
            if p.id == player_id:
                if p.avatar != cleaned:
                    p.avatar = cleaned
                    await self._broadcast(
                        AvatarChanged(player_id=player_id, avatar=cleaned)
                    )
                return
        raise RoomError("unknown player")

    async def add_bot(
        self, difficulty: str = "medium", requester_id: str | None = None
    ) -> Player:
        """Add an AI opponent. `requester_id` None = system (room creation);
        otherwise it's a host action and must be the host, in the lobby."""
        if requester_id is not None:
            if self.host_id != requester_id:
                raise RoomError("only the host can add bots")
            if self.state not in ("lobby", "game_over"):
                raise RoomError("can only add bots in the lobby")
        if difficulty not in BOT_HIT_PROB:
            raise RoomError(f"unknown difficulty: {difficulty}")
        if len(self.players) >= MAX_PLAYERS:
            raise RoomError("the room is full")
        used = {p.name for p in self.players}
        name = next(
            (n for n in BOT_NAMES if n not in used), f"Bot {len(self.players) + 1}"
        )
        bot = Player(id=uuid.uuid4().hex, name=name, is_bot=True)
        self.players.append(bot)
        self.bot_difficulty[bot.id] = difficulty
        self.cumulative_scores[bot.id] = 0
        await self._broadcast(PlayerJoined(player=bot))
        await self._broadcast_pool_state()
        return bot

    async def remove_player(self, player_id: str) -> None:
        """A player's connection dropped (after the reconnect grace)."""
        if not self.has_player(player_id):
            return
        in_game = self.state in (
            "hitster_intro",
            "hitster_listening",
            "hitster_placing",
            "hitster_stealing",
            "hitster_reveal",
            "bingo_spin",
            "bingo_answering",
            "bingo_reveal",
        )
        if in_game and player_id in self.turn_order:
            # Mid-game: keep them in the roster as "offline" (hand + turn slot
            # intact) so the others see they're away and they can resume on
            # reconnect. The rotation skips offline players.
            if player_id in self.disconnected:
                return
            old_host = self.host_id
            was_active_turn = self.current_turn_player_id == player_id
            self.disconnected.add(player_id)
            await self._broadcast(
                ConnectionChanged(
                    disconnected=sorted(self.disconnected), host_id=self.host_id
                )
            )
            if self.host_id != old_host and self.host_id is not None:
                await self._broadcast(HostChanged(host_id=self.host_id))
            # no connected human left → nothing to keep alive (bots can't sustain
            # a room on their own)
            if not self._connected_humans():
                self._cancel_timers()
                await self._on_empty()
                return
            # active player vanished mid-turn (snippet *or* placing) → resolve the
            # turn right away so the table doesn't wait on someone who's gone
            if was_active_turn and self.state in (
                "hitster_listening",
                "hitster_placing",
            ):
                await self._force_resolve_active_turn()
            # bingo: never wait on someone who's gone — their missing answer no
            # longer blocks the early resolve, and a pending mark they earned
            # is auto-placed for them (they answered right before dropping)
            if self.state == "bingo_answering":
                await self._bingo_check_all_answered()
            elif self.state == "bingo_reveal" and (
                player_id in self._bingo_mark_pending
                or player_id in self._bingo_erase_pending
            ):
                await self._bingo_auto_mark(player_id)
                self._bingo_erase_pending.discard(player_id)
                await self._bingo_maybe_finish_marks()
            return
        # lobby / game over / not a participant → remove from the roster
        await self._remove_fully(player_id)

    async def _remove_fully(self, player_id: str) -> None:
        idx = next(
            (i for i, p in enumerate(self.players) if p.id == player_id), None
        )
        if idx is None:
            return
        old_host = self.host_id
        was_active_turn = self.current_turn_player_id == player_id
        self.players.pop(idx)
        self.disconnected.discard(player_id)
        self.bot_difficulty.pop(player_id, None)  # if it was a bot
        # keep hand + turn_order slot so a re-join restores their cards
        await self._broadcast(PlayerLeft(player_id=player_id))
        # no humans left → tear the room down (a bots-only room is pointless)
        if not self._human_players():
            self._cancel_timers()
            await self._on_empty()
            return
        if self.host_id != old_host and self.host_id is not None:
            await self._broadcast(HostChanged(host_id=self.host_id))
        await self._broadcast_pool_state()
        if was_active_turn and self.state in (
            "hitster_listening",
            "hitster_placing",
        ):
            await self._force_resolve_active_turn()

    async def kick_player(self, requester_id: str, target_id: str) -> None:
        """Host removes another player from the room."""
        if self.host_id != requester_id:
            raise RoomError("only the host can kick players")
        if target_id == requester_id:
            raise RoomError("the host cannot kick themselves")
        if not self.has_player(target_id):
            raise RoomError("no such player")
        # Tell the kicked client to leave (so it returns to the landing page and
        # doesn't auto-reconnect), then fully remove them (a kick is permanent,
        # unlike a disconnect which just goes "offline").
        await self._broadcast(PlayerKicked(player_id=target_id))
        await self._remove_fully(target_id)

    # ---------- settings ----------

    async def set_card_target(
        self, requester_id: str, card_target: int
    ) -> None:
        if self.host_id != requester_id:
            raise RoomError("only the host can change the card target")
        if self.state not in ("lobby", "game_over"):
            raise RoomError(
                f"cannot change card target in state {self.state}"
            )
        if (
            card_target < MIN_CARD_TARGET
            or card_target > MAX_CARD_TARGET
        ):
            raise RoomError(
                f"card target must be between {MIN_CARD_TARGET} and {MAX_CARD_TARGET}"
            )
        self.card_target = card_target
        await self._broadcast(CardTargetChanged(card_target=card_target))
        await self._broadcast_pool_state()

    async def set_songs_per_player(
        self, requester_id: str, songs_per_player: int
    ) -> None:
        if self.host_id != requester_id:
            raise RoomError("only the host can change the song limit")
        if self.state not in ("lobby", "game_over"):
            raise RoomError(
                f"cannot change song limit in state {self.state}"
            )
        if (
            songs_per_player < MIN_SONGS_PER_PLAYER
            or songs_per_player > MAX_SONGS_PER_PLAYER
        ):
            raise RoomError(
                f"song limit must be between {MIN_SONGS_PER_PLAYER} "
                f"and {MAX_SONGS_PER_PLAYER}"
            )
        self.songs_per_player = songs_per_player
        await self._broadcast_pool_state()

    async def _broadcast_round_settings(self) -> None:
        await self._broadcast(
            RoundSettingsChanged(
                snippet_duration_s=int(self.snippet_duration_s),
                placing_seconds=int(self.placing_seconds),
                steal_seconds=int(self.steal_seconds),
                starting_cards=self.starting_cards,
            )
        )

    def _require_lobby_host(self, requester_id: str, what: str) -> None:
        if self.host_id != requester_id:
            raise RoomError(f"only the host can change the {what}")
        if self.state not in ("lobby", "game_over"):
            raise RoomError(f"cannot change the {what} in state {self.state}")

    async def set_snippet_duration(
        self, requester_id: str, seconds: int
    ) -> None:
        self._require_lobby_host(requester_id, "snippet length")
        if seconds < MIN_SNIPPET_S or seconds > MAX_SNIPPET_S:
            raise RoomError(
                f"snippet length must be between {MIN_SNIPPET_S} and {MAX_SNIPPET_S}"
            )
        self._snippet_override = seconds
        await self._broadcast_round_settings()

    async def set_placing_seconds(
        self, requester_id: str, seconds: int
    ) -> None:
        self._require_lobby_host(requester_id, "guess time")
        if seconds < MIN_PLACING_S or seconds > MAX_PLACING_S:
            raise RoomError(
                f"guess time must be between {MIN_PLACING_S} and {MAX_PLACING_S}"
            )
        self._placing_override = seconds
        await self._broadcast_round_settings()

    async def set_steal_seconds(self, requester_id: str, seconds: int) -> None:
        self._require_lobby_host(requester_id, "steal time")
        if seconds < MIN_STEAL_S or seconds > MAX_STEAL_S:
            raise RoomError(
                f"steal time must be between {MIN_STEAL_S} and {MAX_STEAL_S}"
            )
        self._steal_override = seconds
        await self._broadcast_round_settings()

    async def set_starting_cards(self, requester_id: str, count: int) -> None:
        self._require_lobby_host(requester_id, "starting cards")
        if count < MIN_STARTING_CARDS or count > MAX_STARTING_CARDS:
            raise RoomError(
                f"starting cards must be between {MIN_STARTING_CARDS} "
                f"and {MAX_STARTING_CARDS}"
            )
        self.starting_cards = count
        await self._broadcast_round_settings()

    async def set_game_mode(self, requester_id: str, mode: GameMode) -> None:
        self._require_lobby_host(requester_id, "game mode")
        if mode not in ("classic", "bingo"):
            raise RoomError(f"unknown game mode: {mode}")
        if self.game_mode != mode:
            self.game_mode = mode
            await self._broadcast(GameModeChanged(mode=mode))

    async def set_bingo_categories(
        self, requester_id: str, categories: list[str]
    ) -> None:
        self._require_lobby_host(requester_id, "bingo categories")
        if len(categories) != 5 or len(set(categories)) != 5:
            raise RoomError("pick exactly 5 different categories")
        unknown = [c for c in categories if c not in CATEGORY_POOL]
        if unknown:
            raise RoomError(f"unknown category(ies): {unknown}")
        self.bingo_categories = list(categories)
        await self._broadcast_bingo_settings()

    async def set_bingo_answer_seconds(
        self, requester_id: str, seconds: int
    ) -> None:
        self._require_lobby_host(requester_id, "answer time")
        if seconds < MIN_BINGO_ANSWER_S or seconds > MAX_BINGO_ANSWER_S:
            raise RoomError(
                f"answer time must be between {MIN_BINGO_ANSWER_S} "
                f"and {MAX_BINGO_ANSWER_S}"
            )
        self._bingo_answer_override = seconds
        await self._broadcast_bingo_settings()

    async def _broadcast_bingo_settings(self) -> None:
        await self._broadcast(
            BingoSettingsChanged(
                categories=list(self.bingo_categories),
                answer_seconds=int(self.bingo_answer_seconds),
            )
        )

    async def set_audio_mode(self, requester_id: str, mode: AudioMode) -> None:
        # host-only, allowed in any state (the couch/online choice is about the
        # physical setup, so the host may flip it before or during a game)
        if self.host_id != requester_id:
            raise RoomError("only the host can change the audio mode")
        if mode not in ("online", "couch"):
            raise RoomError(f"unknown audio mode: {mode}")
        self.audio_mode = mode
        await self._broadcast(AudioModeChanged(mode=mode))

    async def set_steal_enabled(
        self, requester_id: str, enabled: bool
    ) -> None:
        # host-only, any state (an in-progress steal still resolves; this only
        # affects whether the *next* wrong placement opens a steal)
        if self.host_id != requester_id:
            raise RoomError("only the host can change stealing")
        self.steal_enabled = enabled
        await self._broadcast(StealEnabledChanged(enabled=enabled))

    async def set_promo(self, requester_id: str, active: bool) -> None:
        # easter egg — no host check, no state check; whoever knows the secret
        # client-side trigger can toggle it. The triggerer is recorded so they
        # stay ad-free while everyone else in the room gets the overlay.
        self.promo_active = active
        self.promo_by = requester_id if active else None
        await self._broadcast(
            PromoState(active=active, triggered_by=self.promo_by)
        )

    async def set_only_player_added(
        self, requester_id: str, only: bool
    ) -> None:
        if self.host_id != requester_id:
            raise RoomError("only the host can change the song-source toggle")
        if self.state not in ("lobby", "game_over"):
            raise RoomError(
                f"cannot change song source in state {self.state}"
            )
        self.only_player_added = only
        await self._broadcast(OnlyPlayerAddedChanged(only=only))
        await self._broadcast_pool_state()

    async def set_category_filter(
        self, requester_id: str, categories: list[str]
    ) -> None:
        if self.host_id != requester_id:
            raise RoomError("only the host can change categories")
        if self.state not in ("lobby", "game_over"):
            raise RoomError(
                f"cannot change categories in state {self.state}"
            )
        if not categories:
            raise RoomError("at least one category must be selected")
        available = set(self._catalog.available_categories())
        unknown = [c for c in categories if c not in available]
        if unknown:
            raise RoomError(f"unknown category(ies): {unknown}")
        normalized = sorted(set(categories))
        self.category_filter = normalized
        await self._broadcast(CategoryFilterChanged(categories=normalized))
        await self._broadcast_pool_state()

    # ---------- player-added songs ----------

    async def add_song(
        self, player_id: str, raw_track_id: str
    ) -> list[ExtraTrackSummary]:
        if self.state != "lobby":
            raise RoomError(f"cannot add songs in state {self.state}")
        if not self.has_player(player_id):
            raise RoomError("not in this room")
        own_count = sum(
            1 for c in self.extra_tracks.values() if c.added_by_id == player_id
        )
        cap = self.per_player_cap
        # singleplayer: add as many songs as you like (no one to be fair to)
        if not self._is_singleplayer() and own_count >= cap:
            raise RoomError(f"reached your song limit ({cap})")
        track = await itunes_lookup_track(raw_track_id)
        if track is None:
            raise RoomError("could not find that track on iTunes")
        if track.id in self.extra_tracks or self._catalog.has_seed_track(track.id):
            raise RoomError("song already in the pool")
        player_name = next(
            (p.name for p in self.players if p.id == player_id), "?"
        )
        self.extra_tracks[track.id] = ContributedTrack(
            track=track, added_by_id=player_id, added_by_name=player_name
        )
        # persist so the catalog grows with community contributions (survives
        # restarts; merged into the global pool on the next load)
        remember_community_track(track)
        log.info(
            "room %s: %s added %s — %s",
            self.code,
            player_name,
            track.title,
            track.artist,
        )
        record_activity(
            "song_added",
            self.code,
            {"title": track.title, "artist": track.artist, "by": player_name},
        )
        await self._broadcast_pool_state()
        return self._your_extra_tracks(player_id)

    async def remove_song(
        self, player_id: str, raw_track_id: str
    ) -> list[ExtraTrackSummary]:
        if self.state != "lobby":
            raise RoomError(f"cannot remove songs in state {self.state}")
        full_id = f"{EXTRA_TRACK_PREFIX}{raw_track_id}"
        contrib = self.extra_tracks.get(full_id)
        if contrib is None or contrib.added_by_id != player_id:
            raise RoomError("song not found in your contributions")
        del self.extra_tracks[full_id]
        await self._broadcast_pool_state()
        return self._your_extra_tracks(player_id)

    async def set_song_category(
        self, player_id: str, raw_track_id: str, category: str
    ) -> list[ExtraTrackSummary]:
        """Correct the auto-detected category of one of your own added songs.

        Auto-detection (`_detect_category`) is only a guess — this lets the
        contributor flip music<->film_tv. The correction is re-persisted to the
        community pool so it sticks for future games.
        """
        if self.state != "lobby":
            raise RoomError(f"cannot change songs in state {self.state}")
        # fixed known set — a contribution may be film_tv even when no *catalog*
        # track is (e.g. only-player-added mode), so don't gate on the catalog
        if category not in ("music", "film_tv"):
            raise RoomError(f"unknown category: {category}")
        full_id = f"{EXTRA_TRACK_PREFIX}{raw_track_id}"
        contrib = self.extra_tracks.get(full_id)
        if contrib is None or contrib.added_by_id != player_id:
            raise RoomError("song not found in your contributions")
        if contrib.track.category != category:
            new_track = replace(contrib.track, category=category)
            self.extra_tracks[full_id] = replace(contrib, track=new_track)
            remember_community_track(new_track)
            await self._broadcast_pool_state()
        return self._your_extra_tracks(player_id)

    async def _broadcast_pool_state(self) -> None:
        await self._broadcast(
            ExtraTracksTotalChanged(
                extra_tracks_total=len(self.extra_tracks),
                per_player_cap=self.per_player_cap,
                effective_pool_size=self._eligible_pool_size(),
            )
        )

    # ---------- gameplay ----------

    def _fresh_pool(self) -> list[tuple[Track, str | None, str | None]]:
        categories_set = set(self.category_filter)
        pool: list[tuple[Track, str | None, str | None]] = []
        if not self.only_player_added:
            for t in self._catalog.tracks:
                if t.category in categories_set:
                    pool.append((t, None, None))
        for c in self.extra_tracks.values():
            if c.track.category in categories_set:
                pool.append((c.track, c.added_by_id, c.added_by_name))
        return [
            item for item in pool if item[0].id not in self.played_track_ids
        ]

    def _pick_track_no_recycle(
        self,
    ) -> tuple[Track, str | None, str | None] | None:
        fresh = self._fresh_pool()
        if not fresh:
            return None
        # Anti-clustering: avoid the last RECENT_MEMORY tracks this room played
        # (kept across rematches), so the same songs don't keep reappearing —
        # true uniform-random feels repetitive (the Spotify-shuffle problem).
        # Falls back to the full fresh pool when it's too small to be picky.
        recent = set(self.recent_track_ids)
        preferred = [item for item in fresh if item[0].id not in recent]
        pick = random.choice(preferred or fresh)
        self.recent_track_ids.append(pick[0].id)
        if len(self.recent_track_ids) > RECENT_MEMORY:
            del self.recent_track_ids[:-RECENT_MEMORY]
        return pick

    async def start_round(self, requester_id: str) -> None:
        if self.host_id != requester_id:
            raise RoomError("only the host can start a round")
        if self.game_mode == "bingo" or self.state.startswith("bingo"):
            await self._bingo_start_or_advance()
        else:
            await self._hitster_start_or_advance()

    async def _hitster_start_or_advance(self) -> None:
        if self.state == "lobby":
            await self._hitster_start_game()
        elif self.state == "hitster_reveal":
            if self._podium_complete():
                # stale client clicked "next turn" — end gracefully instead
                await self._finish_game()
                return
            await self._hitster_advance_turn()
        else:
            raise RoomError(f"cannot start a turn in state {self.state}")

    def _bump(self, player_id: str, key: str) -> None:
        stats = self.player_stats.get(player_id)
        if stats is not None:
            stats[key] += 1

    def _record_placement_event(
        self,
        player_id: str,
        kind: str,
        slot_index: int | None,
        correct: bool,
    ) -> None:
        """Persist one placement attempt as it happens (see stats.py).

        Must run before the card is awarded — `off_by` (how many years the
        chosen gap missed by) is computed against the placement-time hand.
        """
        track = self.current_track
        player = next((p for p in self.players if p.id == player_id), None)
        if track is None or player is None:
            return
        timed_out = slot_index is None
        off_by: int | None = None
        if correct:
            off_by = 0
        elif slot_index is not None:
            hand = self.hands.get(player_id, [])
            if 0 <= slot_index <= len(hand):
                bounds = [
                    hand[slot_index - 1].year if slot_index > 0 else None,
                    hand[slot_index].year if slot_index < len(hand) else None,
                ]
                distances = [
                    abs(track.year - b) for b in bounds if b is not None
                ]
                off_by = min(distances) if distances else None
        record_placement(
            room_code=self.code,
            kind=kind,
            name=player.name,
            is_bot=player.is_bot,
            singleplayer=self._is_singleplayer(),
            track_id=track.id,
            title=track.title,
            artist=track.artist,
            year=track.year,
            correct=correct,
            timed_out=timed_out,
            off_by=off_by,
        )

    async def _finish_game(self) -> None:
        self.state = "game_over"
        # persist career stats — only games that actually ran (were started)
        if self.turn_order:
            is_bingo = self.game_mode == "bingo"
            if is_bingo:
                # all bingo winners share place 1 (simultaneous marking can
                # legitimately complete two cards in the same round)
                place_of = {pid: 1 for pid in self.bingo_winners}
            else:
                place_of = {
                    pid: i + 1 for i, pid in enumerate(self.finished_players)
                }
            results: list[PlayerResult] = []
            for p in self.players:
                if p.id not in self.turn_order:
                    continue  # spectators never played
                st = self.player_stats.get(p.id, {})
                final_cards = (
                    len(self.bingo_marks.get(p.id, set()))
                    if is_bingo
                    else len(self.hands.get(p.id, []))
                )
                results.append(
                    PlayerResult(
                        name=p.name,
                        is_bot=p.is_bot,
                        place=place_of.get(p.id),
                        final_cards=final_cards,
                        correct=st.get("correct", 0),
                        wrong=st.get("wrong", 0),
                        steals_won=st.get("steals_won", 0),
                        steal_attempts=st.get("steal_attempts", 0),
                    )
                )
            record_game_result(
                room_code=self.code,
                card_target=0 if is_bingo else self.card_target,
                singleplayer=self._is_singleplayer(),
                players=results,
                mode=self.game_mode,
            )
            winner_id = (
                self.finished_players[0] if self.finished_players else None
            )
            record_activity(
                "game_finished",
                self.code,
                {
                    "mode": self.game_mode,
                    "winner": next(
                        (p.name for p in self.players if p.id == winner_id),
                        None,
                    ),
                    "players": len(results),
                    "singleplayer": self._is_singleplayer(),
                },
            )
        await self._broadcast(
            GameOver(
                cumulative_scores=dict(self.cumulative_scores),
                finished_players=list(self.finished_players),
            )
        )

    async def _hitster_start_game(self) -> None:
        n_players = len(self.players)
        if n_players < 1:
            raise RoomError("need at least one player")
        eligible_count = self._eligible_pool_size()
        needed = n_players * self.starting_cards + 1  # starting hands + 1 mystery
        if eligible_count < needed:
            raise RoomError(
                f"need at least {needed} tracks in pool; "
                f"only {eligible_count} match the current filter"
            )

        # shuffle turn order
        player_ids = [p.id for p in self.players]
        random.shuffle(player_ids)
        self.turn_order = player_ids
        self.turn_index = 0

        # deal the starting hand per player (year-sorted into a valid timeline)
        self.hands = {pid: [] for pid in player_ids}
        for pid in player_ids:
            for _ in range(self.starting_cards):
                pick = self._pick_track_no_recycle()
                assert pick is not None  # validated above
                track, _aid, an = pick
                self.played_track_ids.add(track.id)
                self.hands[pid].append(_card_from_track(track, an))
            self.hands[pid].sort(key=lambda c: c.year)

        # update cumulative_scores to mirror card counts
        self.cumulative_scores = {pid: self.starting_cards for pid in player_ids}
        # fresh per-game stat counters for everyone in the rotation
        self.player_stats = {
            pid: {"correct": 0, "wrong": 0, "steals_won": 0, "steal_attempts": 0}
            for pid in player_ids
        }

        names_by_id = {p.id: p.name for p in self.players}
        record_activity(
            "game_started",
            self.code,
            {
                "players": [names_by_id.get(pid, "?") for pid in player_ids],
                "bots": sum(1 for p in self.players if p.is_bot),
                "card_target": self.card_target,
                "starting_cards": self.starting_cards,
                "categories": list(self.category_filter),
                "only_player_added": self.only_player_added,
                "singleplayer": self._is_singleplayer(),
            },
        )

        await self._broadcast(
            HitsterGameStarted(
                turn_order=list(self.turn_order),
                hands={pid: list(cards) for pid, cards in self.hands.items()},
            )
        )

        # pick mystery track for first turn (held back until intro animation finishes)
        pick = self._pick_track_no_recycle()
        if pick is None:
            raise RoomError("no mystery track available")
        track, added_by_id, added_by_name = pick
        self.played_track_ids.add(track.id)
        self.current_track = track
        self.current_track_added_by_id = added_by_id
        self.current_track_added_by_name = added_by_name
        self.last_placement_result = None
        self.state = "hitster_intro"

        first_player = self.turn_order[0]
        log.info(
            "room %s hitster game started; intro -> turn 1: %s, song %s — %s (%d)",
            self.code,
            first_player,
            track.title,
            track.artist,
            track.year,
        )
        # the intro phase delays the snippet so all clients can run the
        # "who-goes-first" animation in lockstep
        self._intro_task = asyncio.create_task(self._hitster_intro_phase())

    async def _hitster_intro_phase(self) -> None:
        try:
            await asyncio.sleep(HITSTER_INTRO_DURATION_S)
        except asyncio.CancelledError:
            return
        if self.state != "hitster_intro":
            return
        track = self.current_track
        if track is None:
            return
        first_player = self.turn_order[self.turn_index]
        self.state = "hitster_listening"
        await self._broadcast(
            HitsterTurnChanged(
                current_turn_player_id=first_player,
                preview_url=track.preview_url,
                snippet_duration_s=self.snippet_duration_s,
            )
        )
        self._snippet_task = asyncio.create_task(self._snippet_phase())

    async def _hitster_advance_turn(self) -> None:
        # finished players keep watching but no longer get turns; offline
        # (disconnected) players are skipped until they reconnect
        finished = set(self.finished_players)
        valid_ids = {
            p.id
            for p in self.players
            if p.id not in finished and p.id not in self.disconnected
        }
        if not any(pid in valid_ids for pid in self.turn_order):
            raise RoomError("no valid players left in turn order")

        # pick before advancing the turn index, so an exhausted pool doesn't
        # silently skip a player
        pick = self._pick_track_no_recycle()
        if pick is None:
            # pool exhausted — the game cannot continue. End it with the
            # current scores instead of stranding the room in the reveal
            # (also rescues clients that still show the next-turn button).
            await self._finish_game()
            return
        track, added_by_id, added_by_name = pick

        # advance to next valid player
        for _ in range(len(self.turn_order)):
            self.turn_index = (self.turn_index + 1) % len(self.turn_order)
            if self.turn_order[self.turn_index] in valid_ids:
                break
        self.played_track_ids.add(track.id)
        self.current_track = track
        self.current_track_added_by_id = added_by_id
        self.current_track_added_by_name = added_by_name
        self.last_placement_result = None
        self.state = "hitster_listening"

        await self._broadcast(
            HitsterTurnChanged(
                current_turn_player_id=self.turn_order[self.turn_index],
                preview_url=track.preview_url,
                snippet_duration_s=self.snippet_duration_s,
            )
        )
        self._snippet_task = asyncio.create_task(self._snippet_phase())

    async def _snippet_phase(self) -> None:
        try:
            await asyncio.sleep(self.snippet_duration_s)
        except asyncio.CancelledError:
            return
        if self.state != "hitster_listening":
            return
        self.state = "hitster_placing"
        active = self.current_turn_player_id
        # a bot "thinks" for a short beat then places itself; a human gets the
        # full guess window and a client-sent placement
        bot_turn = active is not None and self._is_bot(active)
        window = BOT_THINK_S if bot_turn else self.placing_seconds
        deadline_ms = int((time.time() + window) * 1000)
        self._placing_deadline_ms = deadline_ms
        await self._broadcast(PlacingPhase(deadline_ms=deadline_ms))
        if bot_turn:
            self._placing_task = asyncio.create_task(self._bot_place_after(BOT_THINK_S))
        else:
            self._placing_task = asyncio.create_task(self._placing_timeout())

    async def _placing_timeout(self) -> None:
        try:
            await asyncio.sleep(self.placing_seconds)
        except asyncio.CancelledError:
            return
        if self.state != "hitster_placing":
            return
        await self._hitster_reveal(slot_index=None)

    def _bot_slot(self, bot_id: str) -> int:
        """Where the bot places the current card. It knows the true year, so
        difficulty is just P(play the correct gap); otherwise it drops a
        plausible neighbouring (wrong) gap."""
        track = self.current_track
        assert track is not None
        hand = self.hands.get(bot_id, [])
        correct = next(
            (
                i
                for i in range(len(hand) + 1)
                if self._placement_correct(bot_id, i, track.year)
            ),
            0,
        )
        prob = BOT_HIT_PROB.get(self.bot_difficulty.get(bot_id, "medium"), 0.72)
        if random.random() < prob:
            return correct
        neighbours = [
            c
            for c in (correct - 1, correct + 1)
            if 0 <= c <= len(hand)
            and not self._placement_correct(bot_id, c, track.year)
        ]
        wrong = neighbours or [
            i
            for i in range(len(hand) + 1)
            if not self._placement_correct(bot_id, i, track.year)
        ]
        return random.choice(wrong) if wrong else correct

    async def _bot_place_after(self, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        if self.state != "hitster_placing":
            return
        active = self.current_turn_player_id
        if active is None or not self._is_bot(active):
            return
        await self._hitster_reveal(slot_index=self._bot_slot(active))

    async def _force_resolve_active_turn(self) -> None:
        """Reveal the current turn as a miss from either listening or placing.

        Used when the active player leaves mid-turn: cancel the running timers
        and jump straight to the reveal so the round can move on without the
        others waiting out the snippet + placing timeout.
        """
        self._cancel_timers()
        if self.state == "hitster_listening":
            # _hitster_reveal only proceeds from "placing"; step into it first
            self.state = "hitster_placing"
            self._placing_deadline_ms = None
        await self._hitster_reveal(slot_index=None)

    async def place_song(self, player_id: str, slot_index: int) -> None:
        if self.state != "hitster_placing":
            raise RoomError(f"cannot place in state {self.state}")
        if player_id != self.current_turn_player_id:
            raise RoomError("not your turn")
        hand = self.hands.get(player_id, [])
        if slot_index < 0 or slot_index > len(hand):
            raise RoomError("invalid slot")
        if self._placing_task is not None:
            self._placing_task.cancel()
        await self._hitster_reveal(slot_index=slot_index)

    def _placement_correct(
        self, player_id: str, slot_index: int | None, year: int
    ) -> bool:
        """Does placing a card of `year` at `slot_index` fit player's timeline?"""
        if slot_index is None:
            return False
        hand = self.hands.get(player_id, [])
        if slot_index < 0 or slot_index > len(hand):
            return False
        lower = hand[slot_index - 1].year if slot_index > 0 else float("-inf")
        upper = hand[slot_index].year if slot_index < len(hand) else float("inf")
        return lower <= year <= upper

    def _award_card(self, player_id: str, slot_index: int | None) -> int | None:
        """Give player the current mystery card at slot_index; return their new
        podium place if this reaches the card target, else None."""
        track = self.current_track
        assert track is not None
        card = _card_from_track(track, self.current_track_added_by_name)
        if slot_index is not None and player_id in self.hands:
            self.hands[player_id].insert(slot_index, card)
        if (
            player_id not in self.finished_players
            and len(self.hands.get(player_id, [])) >= self.card_target
        ):
            self.finished_players.append(player_id)
            return len(self.finished_players)
        return None

    def _steal_eligible_ids(self) -> list[str]:
        """Players who may steal the current miss: everyone in the rotation
        except the one who missed, podium finishers and offline players."""
        return [
            pid
            for pid in self.turn_order
            if pid != self._steal_placer_id
            and pid not in self.finished_players
            and pid not in self.disconnected
            and self.has_player(pid)
        ]

    async def _hitster_reveal(self, slot_index: int | None) -> None:
        if self.state != "hitster_placing":
            return
        track = self.current_track
        placer_id = self.current_turn_player_id
        assert track is not None
        assert placer_id is not None

        correct = self.has_player(placer_id) and self._placement_correct(
            placer_id, slot_index, track.year
        )

        self._bump(placer_id, "correct" if correct else "wrong")
        self._record_placement_event(placer_id, "turn", slot_index, correct)

        # remember the active attempt for the (possibly deferred) reveal
        self._steal_placer_id = placer_id
        self._active_slot_index = slot_index
        self._active_correct = correct
        self._active_finished_place = None
        self._steal_winner_id = None
        self._steal_finished_place = None
        self._placing_deadline_ms = None

        # a miss opens the steal race (when enabled and someone can steal);
        # a correct placement is awarded immediately and revealed
        if not correct and self.steal_enabled and self._steal_eligible_ids():
            await self._open_steal()
            return
        if correct:
            self._active_finished_place = self._award_card(placer_id, slot_index)
        await self._finalize_reveal(steal_offered=False)

    async def _open_steal(self) -> None:
        self.state = "hitster_stealing"
        self._steal_attempted = set()
        deadline_ms = int((time.time() + self.steal_seconds) * 1000)
        self._steal_deadline_ms = deadline_ms
        log.info(
            "room %s steal opened: %s missed, %d can steal",
            self.code,
            self._steal_placer_id,
            len(self._steal_eligible_ids()),
        )
        await self._broadcast(
            StealStarted(
                placer_id=self._steal_placer_id or "", deadline_ms=deadline_ms
            )
        )
        self._steal_task = asyncio.create_task(self._steal_timeout())
        # bots race too, each after a random beat so a human can beat them to it
        self._bot_steal_tasks = [
            asyncio.create_task(self._bot_steal(pid))
            for pid in self._steal_eligible_ids()
            if self._is_bot(pid)
        ]

    async def _bot_steal(self, bot_id: str) -> None:
        # wait a random slice of the window (leaving the human a chance to be first)
        upper = max(1.0, min(self.steal_seconds - 1, 6))
        try:
            await asyncio.sleep(random.uniform(0.8, upper))
        except asyncio.CancelledError:
            return
        if self.state != "hitster_stealing" or self._steal_winner_id is not None:
            return
        if bot_id in self._steal_attempted or bot_id not in self._steal_eligible_ids():
            return
        try:
            await self.steal_place(bot_id, self._bot_slot(bot_id))
        except RoomError:
            pass

    async def _steal_timeout(self) -> None:
        try:
            await asyncio.sleep(self.steal_seconds)
        except asyncio.CancelledError:
            return
        if self.state != "hitster_stealing":
            return
        await self._finalize_reveal(steal_offered=True)

    async def steal_place(self, player_id: str, slot_index: int) -> None:
        if self.state != "hitster_stealing":
            raise RoomError(f"cannot steal in state {self.state}")
        if player_id not in self._steal_eligible_ids():
            raise RoomError("you can't steal this turn")
        if player_id in self._steal_attempted:
            raise RoomError("you already tried to steal")
        hand = self.hands.get(player_id, [])
        if slot_index < 0 or slot_index > len(hand):
            raise RoomError("invalid slot")
        track = self.current_track
        assert track is not None

        self._steal_attempted.add(player_id)
        self._bump(player_id, "steal_attempts")
        steal_correct = self._placement_correct(player_id, slot_index, track.year)
        self._record_placement_event(player_id, "steal", slot_index, steal_correct)
        if steal_correct:
            # first correct placement wins the race → straight to the reveal
            self._steal_winner_id = player_id
            self._steal_finished_place = self._award_card(player_id, slot_index)
            self._bump(player_id, "steals_won")
            self._cancel_timers()
            await self._finalize_reveal(steal_offered=True)
            return
        # wrong — they're out; the race continues for everyone else
        await self._broadcast(StealAttempted(player_id=player_id))
        if all(pid in self._steal_attempted for pid in self._steal_eligible_ids()):
            # everyone has tried and missed → no steal, reveal now
            self._cancel_timers()
            await self._finalize_reveal(steal_offered=True)

    async def _finalize_reveal(self, steal_offered: bool) -> None:
        track = self.current_track
        placer_id = self._steal_placer_id
        assert track is not None
        assert placer_id is not None

        new_card = _card_from_track(track, self.current_track_added_by_name)
        card_counts = {
            p.id: len(self.hands.get(p.id, [])) for p in self.players
        }
        self.cumulative_scores = dict(card_counts)
        game_finished = self._podium_complete()
        winner = self._steal_winner_id

        result = PlacementResult(
            placer_id=placer_id,
            slot_index=self._active_slot_index,
            correct=self._active_correct,
            card=new_card,
            placer_new_hand=list(self.hands.get(placer_id, [])),
            card_counts=card_counts,
            placer_finished_place=self._active_finished_place,
            finished_players=list(self.finished_players),
            game_finished=game_finished,
            pool_exhausted=not self._fresh_pool(),
            steal_offered=steal_offered,
            stolen_by=winner,
            stealer_new_hand=(
                list(self.hands.get(winner, [])) if winner else None
            ),
            stealer_finished_place=self._steal_finished_place,
        )
        self.last_placement_result = result
        self.state = "hitster_reveal"
        self._placing_deadline_ms = None
        self._steal_deadline_ms = None
        log.info(
            "room %s reveal: %s correct=%s year=%d stolen_by=%s finished=%s",
            self.code,
            placer_id,
            self._active_correct,
            track.year,
            winner,
            game_finished,
        )
        await self._broadcast(result)

    # ---------- bingo mode ----------
    # No turns: the disco-ball wheel picks a category (bingo_spin), everyone
    # answers the same song simultaneously (bingo_answering), the reveal shows
    # all answers and correct players mark a cell of the drawn colour on their
    # 5x5 card (bingo_reveal doubles as the marking phase, with a timeout
    # auto-pick), then the next spin follows automatically. First full
    # row/column/diagonal wins. Rules live in bingo.py; this is orchestration.

    async def _bingo_start_or_advance(self) -> None:
        if self.state == "lobby":
            await self._bingo_start_game()
        elif (
            self.state == "bingo_reveal"
            and not self._bingo_mark_pending
            and not self._bingo_erase_pending
            and (self._bingo_task is None or self._bingo_task.done())
        ):
            # a restored room paused on its reveal — the host nudges it on
            await self._bingo_next_round()
        else:
            raise RoomError(f"cannot start a bingo round in state {self.state}")

    def _bingo_active_ids(self) -> list[str]:
        """Participants whose answer the round waits for (bots count; offline
        humans don't — they simply score a miss)."""
        return [
            pid
            for pid in self.turn_order
            if self.has_player(pid) and pid not in self.disconnected
        ]

    async def _bingo_start_game(self) -> None:
        if len(self.players) < 1:
            raise RoomError("need at least one player")
        eligible_count = self._eligible_pool_size()
        if eligible_count < BINGO_MIN_POOL:
            raise RoomError(
                f"need at least {BINGO_MIN_POOL} tracks in pool; "
                f"only {eligible_count} match the current filter"
            )
        if len(self.bingo_categories) != 5:
            raise RoomError("bingo needs exactly 5 categories")

        player_ids = [p.id for p in self.players]
        random.shuffle(player_ids)
        self.turn_order = player_ids
        self.turn_index = 0
        self.hands = {}
        self.finished_players = []
        self.bingo_cards = {pid: generate_card() for pid in player_ids}
        self.bingo_marks = {pid: set() for pid in player_ids}
        self.bingo_round = 0
        self.bingo_winners = []
        self._bingo_prev_title = None
        self._bingo_prev_year = None
        self.cumulative_scores = {pid: 0 for pid in player_ids}
        self.player_stats = {
            pid: {"correct": 0, "wrong": 0, "steals_won": 0, "steal_attempts": 0}
            for pid in player_ids
        }

        names_by_id = {p.id: p.name for p in self.players}
        record_activity(
            "game_started",
            self.code,
            {
                "mode": "bingo",
                "players": [names_by_id.get(pid, "?") for pid in player_ids],
                "bots": sum(1 for p in self.players if p.is_bot),
                "categories": list(self.bingo_categories),
                "only_player_added": self.only_player_added,
                "singleplayer": self._is_singleplayer(),
            },
        )
        await self._broadcast(
            BingoGameStarted(
                participants=list(player_ids),
                cards={pid: list(c) for pid, c in self.bingo_cards.items()},
                categories=list(self.bingo_categories),
            )
        )
        await self._bingo_next_round()

    async def _bingo_next_round(self) -> None:
        pick = self._pick_track_no_recycle()
        if pick is None:
            # pool ran dry before anyone made a bingo — most marks wins
            await self._bingo_finish()
            return
        track, added_by_id, added_by_name = pick
        # last round's song becomes the Zeitduell pivot (revealed = public);
        # after a checkpoint restore current_track is None and the pivot was
        # already rebuilt from last_bingo_result in from_persist
        if self.bingo_round >= 1 and self.current_track is not None:
            self._bingo_prev_title = self.current_track.title
            self._bingo_prev_year = self.current_track.year
        self.played_track_ids.add(track.id)
        self.current_track = track
        self.current_track_added_by_id = added_by_id
        self.current_track_added_by_name = added_by_name
        self.bingo_round += 1
        # vs_prev needs a previous song — keep its slot out of the first draw
        # (indexing into the eligible list keeps the tests' pinned randrange
        # working: with no vs_prev pick this is the old randrange(5))
        slots = [
            i
            for i, cid in enumerate(self.bingo_categories)
            if self._bingo_prev_year is not None
            or CATEGORY_POOL[cid].kind != "vs_prev"
        ] or list(range(len(self.bingo_categories)))
        self._bingo_category_idx = slots[random.randrange(len(slots))]
        self._bingo_answers = {}
        self._bingo_deadline_ms = None
        self._bingo_mark_pending = set()
        self._bingo_erase_pending = set()
        self.last_bingo_result = None
        self.state = "bingo_spin"
        log.info(
            "room %s bingo round %d: category %s, song %s — %s (%d)",
            self.code,
            self.bingo_round,
            self.bingo_categories[self._bingo_category_idx],
            track.title,
            track.artist,
            track.year,
        )
        await self._broadcast(
            BingoSpin(
                round=self.bingo_round,
                category_index=self._bingo_category_idx,
                prev_title=self._bingo_prev_title,
                prev_year=self._bingo_prev_year,
            )
        )
        self._bingo_task = asyncio.create_task(self._bingo_spin_phase())

    async def _bingo_spin_phase(self) -> None:
        try:
            await asyncio.sleep(BINGO_SPIN_S)
        except asyncio.CancelledError:
            return
        if self.state != "bingo_spin":
            return
        track = self.current_track
        if track is None:
            return
        self.state = "bingo_answering"
        deadline_ms = int((time.time() + self.bingo_answer_seconds) * 1000)
        self._bingo_deadline_ms = deadline_ms
        await self._broadcast(
            BingoAnswering(
                deadline_ms=deadline_ms, preview_url=track.preview_url
            )
        )
        self._bingo_task = asyncio.create_task(self._bingo_answer_timeout())
        self._bot_bingo_tasks = [
            asyncio.create_task(self._bot_bingo_answer(pid))
            for pid in self.turn_order
            if self._is_bot(pid)
        ]

    async def _bingo_answer_timeout(self) -> None:
        try:
            await asyncio.sleep(self.bingo_answer_seconds)
        except asyncio.CancelledError:
            return
        if self.state != "bingo_answering":
            return
        self._cancel_bingo_round_tasks()
        await self._bingo_resolve()

    async def _bot_bingo_answer(self, bot_id: str) -> None:
        upper = max(3.0, min(self.bingo_answer_seconds * 0.6, 12.0))
        try:
            await asyncio.sleep(random.uniform(2.0, upper))
        except asyncio.CancelledError:
            return
        if self.state != "bingo_answering" or bot_id in self._bingo_answers:
            return
        track = self.current_track
        cat_idx = self._bingo_category_idx
        if track is None or cat_idx is None:
            return
        prob = BOT_HIT_PROB.get(self.bot_difficulty.get(bot_id, "medium"), 0.72)
        value = bot_answer(
            CATEGORY_POOL[self.bingo_categories[cat_idx]],
            track.year,
            track.title,
            track.artist,
            hit=random.random() < prob,
            prev_year=self._bingo_prev_year,
        )
        try:
            await self.submit_bingo_answer(bot_id, value)
        except RoomError:
            pass

    async def submit_bingo_answer(self, player_id: str, value: str) -> None:
        if self.state != "bingo_answering":
            raise RoomError(f"cannot answer in state {self.state}")
        if player_id not in self.turn_order:
            raise RoomError("you're spectating this game")
        # resubmitting overwrites until the deadline (or until everyone is in)
        self._bingo_answers[player_id] = value.strip()[:120]
        await self._broadcast(
            BingoAnswered(
                player_id=player_id, answered=sorted(self._bingo_answers)
            )
        )
        await self._bingo_check_all_answered()

    async def _bingo_check_all_answered(self) -> None:
        if self.state != "bingo_answering":
            return
        if all(pid in self._bingo_answers for pid in self._bingo_active_ids()):
            self._cancel_bingo_round_tasks()
            await self._bingo_resolve()

    async def _bingo_resolve(self) -> None:
        if self.state != "bingo_answering":
            return
        track = self.current_track
        cat_idx = self._bingo_category_idx
        assert track is not None
        assert cat_idx is not None
        cat = CATEGORY_POOL[self.bingo_categories[cat_idx]]
        self.state = "bingo_reveal"
        self._bingo_deadline_ms = None
        if self._bingo_answers:
            self._bingo_idle_rounds = 0
        else:
            self._bingo_idle_rounds += 1

        # closest_year is a bet across ALL answers, not a per-player check
        closest_winners: set[str] = set()
        if cat.kind == "closest_year":
            closest_winners = closest_year_winners(
                {pid: self._bingo_answers.get(pid) for pid in self.turn_order},
                track.year,
            )

        results: list[BingoPlayerResult] = []
        for pid in self.turn_order:
            player = next((p for p in self.players if p.id == pid), None)
            if player is None:
                continue
            raw = self._bingo_answers.get(pid)
            if cat.kind == "closest_year":
                correct = pid in closest_winners
                exact = correct and bingo_off_by(cat, raw, track.year) == 0
            else:
                correct, exact = evaluate_answer(
                    cat,
                    track.year,
                    track.title,
                    track.artist,
                    raw or "",
                    prev_year=self._bingo_prev_year,
                )
            self._bump(pid, "correct" if correct else "wrong")
            record_placement(
                room_code=self.code,
                kind=f"bingo_{cat.id}",
                name=player.name,
                is_bot=player.is_bot,
                singleplayer=self._is_singleplayer(),
                track_id=track.id,
                title=track.title,
                artist=track.artist,
                year=track.year,
                correct=correct,
                timed_out=raw is None,
                off_by=bingo_off_by(cat, raw, track.year),
            )
            results.append(
                BingoPlayerResult(
                    player_id=pid,
                    answer=raw or "",
                    correct=correct,
                    exact=exact,
                )
            )
            if correct:
                free_cell = best_mark_cell(
                    self.bingo_cards.get(pid, []),
                    self.bingo_marks.setdefault(pid, set()),
                    cat_idx,
                )
                if free_cell is not None:
                    self._bingo_mark_pending.add(pid)
            if exact and pid not in self.disconnected:
                # the erase bonus needs a victim with at least one mark
                if any(
                    marks and other != pid
                    for other, marks in self.bingo_marks.items()
                ):
                    self._bingo_erase_pending.add(pid)

        # offline earners get their mark auto-placed (they answered correctly
        # before dropping) — only connected players are actually waited on
        offline_earned = [
            pid
            for pid in sorted(self._bingo_mark_pending)
            if pid in self.disconnected
        ]
        interactive = (
            self._bingo_mark_pending - set(offline_earned)
        ) | self._bingo_erase_pending
        mark_deadline = (
            int((time.time() + BINGO_MARK_S) * 1000) if interactive else None
        )
        self._bingo_deadline_ms = mark_deadline
        result = BingoRoundResult(
            round=self.bingo_round,
            category_index=cat_idx,
            card=_card_from_track(track, self.current_track_added_by_name),
            results=results,
            mark_deadline_ms=mark_deadline,
            mark_pending=sorted(self._bingo_mark_pending),
            erase_pending=sorted(self._bingo_erase_pending),
        )
        self.last_bingo_result = result
        log.info(
            "room %s bingo reveal r%d: %d/%d correct, exact=%d",
            self.code,
            self.bingo_round,
            sum(1 for r in results if r.correct),
            len(results),
            sum(1 for r in results if r.exact),
        )
        await self._broadcast(result)
        for pid in offline_earned:
            await self._bingo_auto_mark(pid)
        if self._bingo_mark_pending or self._bingo_erase_pending:
            self._bingo_task = asyncio.create_task(self._bingo_mark_timeout())
            self._bot_bingo_tasks = [
                asyncio.create_task(self._bot_bingo_mark(pid))
                for pid in sorted(
                    self._bingo_mark_pending | self._bingo_erase_pending
                )
                if self._is_bot(pid)
            ]
        else:
            await self._bingo_round_done()

    async def bingo_mark(self, player_id: str, cell: int) -> None:
        if self.state != "bingo_reveal":
            raise RoomError(f"cannot mark in state {self.state}")
        if player_id not in self._bingo_mark_pending:
            raise RoomError("no mark to place")
        cat_idx = self._bingo_category_idx
        assert cat_idx is not None
        card = self.bingo_cards.get(player_id, [])
        if cell < 0 or cell >= len(card):
            raise RoomError("invalid cell")
        if card[cell] != cat_idx:
            raise RoomError("that cell is not this round's colour")
        marks = self.bingo_marks.setdefault(player_id, set())
        if cell in marks:
            raise RoomError("cell already marked")
        marks.add(cell)
        self._bingo_mark_pending.discard(player_id)
        await self._broadcast_bingo_marks(
            player_id, actor_id=player_id, erased=False
        )
        await self._bingo_maybe_finish_marks()

    async def bingo_erase(
        self, player_id: str, target_id: str | None, cell: int | None
    ) -> None:
        if self.state != "bingo_reveal":
            raise RoomError(f"cannot erase in state {self.state}")
        if player_id not in self._bingo_erase_pending:
            raise RoomError("no erase available")
        if target_id is None:
            # passing on the bonus is allowed (and kinder among friends)
            self._bingo_erase_pending.discard(player_id)
            await self._broadcast_bingo_marks(
                None, actor_id=player_id, erased=False
            )
            await self._bingo_maybe_finish_marks()
            return
        if target_id == player_id:
            raise RoomError("cannot erase your own mark")
        target_marks = self.bingo_marks.get(target_id)
        if target_marks is None:
            raise RoomError("no such player")
        if cell is None or cell not in target_marks:
            raise RoomError("that cell isn't marked")
        target_marks.discard(cell)
        self._bingo_erase_pending.discard(player_id)
        await self._broadcast_bingo_marks(
            target_id, actor_id=player_id, erased=True
        )
        await self._bingo_maybe_finish_marks()

    async def _bingo_auto_mark(self, player_id: str) -> None:
        """Best-cell auto-pick for someone who can't (offline) or didn't
        (timeout) choose — dozing off still helps you."""
        if player_id not in self._bingo_mark_pending:
            return
        self._bingo_mark_pending.discard(player_id)
        cat_idx = self._bingo_category_idx
        if cat_idx is None:
            return
        cell = best_mark_cell(
            self.bingo_cards.get(player_id, []),
            self.bingo_marks.setdefault(player_id, set()),
            cat_idx,
        )
        if cell is None:
            return
        self.bingo_marks[player_id].add(cell)
        await self._broadcast_bingo_marks(
            player_id, actor_id=None, erased=False
        )

    async def _bingo_mark_timeout(self) -> None:
        try:
            await asyncio.sleep(BINGO_MARK_S)
        except asyncio.CancelledError:
            return
        if self.state != "bingo_reveal":
            return
        self._cancel_bingo_round_tasks()
        for pid in sorted(self._bingo_mark_pending):
            await self._bingo_auto_mark(pid)
        self._bingo_erase_pending = set()  # unused erases just lapse
        await self._bingo_round_done()

    async def _bingo_maybe_finish_marks(self) -> None:
        # only closes an *active* marking window (deadline set); the linger
        # after a resolved round must not be re-triggerable
        if self.state != "bingo_reveal" or self._bingo_deadline_ms is None:
            return
        if self._bingo_mark_pending or self._bingo_erase_pending:
            return
        self._cancel_bingo_round_tasks()
        await self._bingo_round_done()

    async def _bot_bingo_mark(self, bot_id: str) -> None:
        try:
            await asyncio.sleep(random.uniform(1.5, 5.0))
        except asyncio.CancelledError:
            return
        if self.state != "bingo_reveal":
            return
        cat_idx = self._bingo_category_idx
        if cat_idx is None:
            return
        if bot_id in self._bingo_mark_pending:
            cell = best_mark_cell(
                self.bingo_cards.get(bot_id, []),
                self.bingo_marks.get(bot_id, set()),
                cat_idx,
            )
            if cell is not None:
                try:
                    await self.bingo_mark(bot_id, cell)
                except RoomError:
                    pass
        if bot_id in self._bingo_erase_pending:
            target = best_erase(self.bingo_marks, exclude=bot_id)
            try:
                if target is None:
                    await self.bingo_erase(bot_id, None, None)
                else:
                    await self.bingo_erase(bot_id, target[0], target[1])
            except RoomError:
                pass

    async def _broadcast_bingo_marks(
        self, player_id: str | None, actor_id: str | None, erased: bool
    ) -> None:
        counts = {
            pid: len(self.bingo_marks.get(pid, set()))
            for pid in self.turn_order
            if self.has_player(pid)
        }
        self.cumulative_scores = dict(counts)
        await self._broadcast(
            BingoMarksChanged(
                player_id=player_id,
                marks=(
                    sorted(self.bingo_marks.get(player_id, set()))
                    if player_id is not None
                    else None
                ),
                actor_id=actor_id,
                erased=erased,
                card_counts=counts,
                mark_pending=sorted(self._bingo_mark_pending),
                erase_pending=sorted(self._bingo_erase_pending),
            )
        )

    async def _bingo_round_done(self) -> None:
        self._bingo_deadline_ms = None
        marks_out = {
            pid: sorted(marks)
            for pid, marks in self.bingo_marks.items()
            if self.has_player(pid)
        }
        counts = {pid: len(marks) for pid, marks in marks_out.items()}
        self.cumulative_scores = dict(counts)
        winners = [
            pid
            for pid in self.turn_order
            if self.has_player(pid)
            and has_bingo(self.bingo_marks.get(pid, set()))
        ]
        await self._broadcast(
            BingoRoundDone(marks=marks_out, card_counts=counts, winners=winners)
        )
        if winners:
            self.bingo_winners = winners
            await self._bingo_finish()
        elif self._bingo_idle_rounds >= BINGO_IDLE_ROUNDS:
            # everyone's gone quiet (tab left open on the table) — end the
            # game instead of churning through the pool on autopilot
            log.info(
                "room %s bingo idle for %d rounds — ending game",
                self.code,
                self._bingo_idle_rounds,
            )
            await self._bingo_finish()
        else:
            self._bingo_task = asyncio.create_task(
                self._bingo_linger_then_next()
            )

    async def _bingo_linger_then_next(self) -> None:
        try:
            await asyncio.sleep(BINGO_LINGER_S)
        except asyncio.CancelledError:
            return
        if self.state != "bingo_reveal":
            return
        await self._bingo_next_round()

    async def _bingo_finish(self) -> None:
        """Game over — someone made a bingo, or the pool ran dry (then most
        marks wins; ties share the win). Ranking: winners, then marks desc."""
        if not self.bingo_winners:
            best_count = max(
                (
                    len(self.bingo_marks.get(pid, set()))
                    for pid in self.turn_order
                    if self.has_player(pid)
                ),
                default=0,
            )
            if best_count > 0:
                self.bingo_winners = [
                    pid
                    for pid in self.turn_order
                    if self.has_player(pid)
                    and len(self.bingo_marks.get(pid, set())) == best_count
                ]
        rest = sorted(
            (
                pid
                for pid in self.turn_order
                if self.has_player(pid) and pid not in self.bingo_winners
            ),
            key=lambda pid: -len(self.bingo_marks.get(pid, set())),
        )
        self.finished_players = list(self.bingo_winners) + rest
        await self._finish_game()

    def _cancel_bingo_round_tasks(self) -> None:
        # never cancel the task we're running IN (a bot task calling into the
        # engine) — the CancelledError would gut the reveal mid-broadcast
        current = asyncio.current_task()
        for task in (self._bingo_task, *self._bot_bingo_tasks):
            if task is not None and task is not current and not task.done():
                task.cancel()

    # ---------- end / rematch ----------

    async def end_game(self, requester_id: str) -> None:
        if self.host_id != requester_id:
            raise RoomError("only the host can end the game")
        if self.state != "hitster_reveal":
            raise RoomError(f"cannot end game in state {self.state}")
        if not self._podium_complete() and self._fresh_pool():
            raise RoomError("podium not decided and tracks remain")
        await self._finish_game()

    def _reset_to_lobby(self) -> list[str]:
        """Reset to a fresh lobby; returns the ids of pruned offline players.

        Players still flagged offline don't carry into the next lobby — same
        rule as a lobby disconnect (fully removed; a rejoin re-adds them
        cleanly). Without this they'd become ghosts in the next game's
        turn_order. Also the rule for rooms restored from a checkpoint, where
        everyone starts offline.
        """
        self._cancel_timers()
        pruned = [p.id for p in self.players if p.id in self.disconnected]
        self.players = [p for p in self.players if p.id not in self.disconnected]
        self.disconnected = set()
        self.cumulative_scores = {p.id: 0 for p in self.players}
        self.played_track_ids = set()
        self.last_placement_result = None
        self.current_track = None
        self.current_track_added_by_id = None
        self.current_track_added_by_name = None
        self.hands = {}
        self.turn_order = []
        self.turn_index = 0
        self.finished_players = []
        self.player_stats = {}
        self._placing_deadline_ms = None
        self._steal_deadline_ms = None
        self._steal_placer_id = None
        self._steal_attempted = set()
        self._steal_winner_id = None
        self.bingo_cards = {}
        self.bingo_marks = {}
        self.bingo_round = 0
        self.bingo_winners = []
        self._bingo_idle_rounds = 0
        self.last_bingo_result = None
        self._bingo_category_idx = None
        self._bingo_prev_title = None
        self._bingo_prev_year = None
        self._bingo_answers = {}
        self._bingo_deadline_ms = None
        self._bingo_mark_pending = set()
        self._bingo_erase_pending = set()
        self.state = "lobby"
        return pruned

    async def _announce_lobby_reset(self, pruned: list[str]) -> None:
        # clients route RematchStarted to the lobby; pruned offline players
        # are announced afterwards so every roster drops them too
        await self._broadcast(RematchStarted())
        for pid in pruned:
            await self._broadcast(PlayerLeft(player_id=pid))

    async def rematch(self, requester_id: str) -> None:
        if self.host_id != requester_id:
            raise RoomError("only the host can start a rematch")
        if self.state != "game_over":
            raise RoomError(f"cannot rematch in state {self.state}")
        await self._announce_lobby_reset(self._reset_to_lobby())

    async def abort_to_lobby(self, requester_id: str) -> None:
        """Host aborts the running game and returns everyone to the lobby."""
        if self.host_id != requester_id:
            raise RoomError("only the host can abort the game")
        if self.state == "lobby":
            raise RoomError("already in the lobby")
        if self.state != "game_over":
            record_activity("game_aborted", self.code, {"state": self.state})
        # the lobby reset is identical to a rematch; reuse the client handling
        await self._announce_lobby_reset(self._reset_to_lobby())

    # ---------- host score adjustments ----------

    async def _broadcast_cards_adjusted(self, player_id: str) -> None:
        card_counts = {p.id: len(self.hands.get(p.id, [])) for p in self.players}
        self.cumulative_scores = dict(card_counts)
        await self._broadcast(
            CardsAdjusted(
                player_id=player_id,
                hand=list(self.hands.get(player_id, [])),
                card_counts=card_counts,
            )
        )

    async def give_card(self, requester_id: str, target_id: str) -> None:
        """Host grants a player a card (a random fresh song, now out of the pool)."""
        if self.host_id != requester_id:
            raise RoomError("only the host can adjust scores")
        if self.state in ("lobby", "game_over"):
            raise RoomError("can only adjust scores during a game")
        if self.state.startswith("bingo"):
            raise RoomError("card adjustments don't exist in bingo")
        if not self.has_player(target_id):
            raise RoomError("no such player")
        pick = self._pick_track_no_recycle()
        if pick is None:
            raise RoomError("no fresh songs left to give")
        track, _added_by_id, added_by_name = pick
        self.played_track_ids.add(track.id)
        card = _card_from_track(track, added_by_name)
        hand = self.hands.setdefault(target_id, [])
        # keep the timeline year-sorted
        idx = 0
        while idx < len(hand) and hand[idx].year <= card.year:
            idx += 1
        hand.insert(idx, card)
        await self._broadcast_cards_adjusted(target_id)

    async def take_card(self, requester_id: str, target_id: str) -> None:
        """Host removes a random card from a player (never below 1)."""
        if self.host_id != requester_id:
            raise RoomError("only the host can adjust scores")
        if self.state in ("lobby", "game_over"):
            raise RoomError("can only adjust scores during a game")
        if self.state.startswith("bingo"):
            raise RoomError("card adjustments don't exist in bingo")
        if not self.has_player(target_id):
            raise RoomError("no such player")
        hand = self.hands.get(target_id, [])
        if len(hand) <= 1:
            raise RoomError("player is already at 1 card")
        hand.pop(random.randrange(len(hand)))
        await self._broadcast_cards_adjusted(target_id)

    def _cancel_timers(self) -> None:
        current = asyncio.current_task()
        tasks = [
            self._snippet_task,
            self._placing_task,
            self._intro_task,
            self._steal_task,
            *self._bot_steal_tasks,
            self._bingo_task,
            *self._bot_bingo_tasks,
        ]
        for task in tasks:
            # never cancel the task we're running in (e.g. a bot task calling
            # into the engine) — the CancelledError would gut the reveal
            if task is not None and task is not current and not task.done():
                task.cancel()


def _card_from_track(track: Track, added_by: str | None) -> CardSnapshot:
    return CardSnapshot(
        track_id=track.id,
        title=track.title,
        artist=track.artist,
        year=track.year,
        artwork_url=track.artwork_url,
        added_by=added_by,
    )
