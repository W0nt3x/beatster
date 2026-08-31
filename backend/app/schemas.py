from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

RoomState = Literal[
    "lobby",
    "hitster_intro",
    "hitster_listening",
    "hitster_placing",
    "hitster_stealing",
    "hitster_reveal",
    "bingo_spin",
    "bingo_answering",
    "bingo_reveal",
    "game_over",
]

# which rules the next game uses (lobby mode tiles); per-room, host-set
GameMode = Literal["classic", "bingo"]

# where the snippet audio plays:
#   "online" — every player's device plays (default, remote play)
#   "couch"  — only the host's device plays (one shared screen/speaker)
AudioMode = Literal["online", "couch"]


class Player(BaseModel):
    id: str
    name: str
    is_bot: bool = False  # server-controlled AI opponent (singleplayer)
    # avatar identifier chosen by the player, e.g. "fun-emoji:x7Kp2" (DiceBear
    # style:seed, rendered client-side) or "img:<file>" (bundled meme catalog).
    # "" = client default (fun-emoji seeded by name; bots always render bottts).
    avatar: str = ""


# ---------- client -> server ----------


class Join(BaseModel):
    type: Literal["join"] = "join"
    name: str
    player_id: str | None = None
    avatar: str = ""  # stored preference, re-announced on every (re)join


class SetAvatar(BaseModel):
    type: Literal["set_avatar"] = "set_avatar"
    avatar: str


class StartRound(BaseModel):
    type: Literal["start_round"] = "start_round"


class SetCategoryFilter(BaseModel):
    type: Literal["set_category_filter"] = "set_category_filter"
    categories: list[str]


class SetOnlyPlayerAdded(BaseModel):
    type: Literal["set_only_player_added"] = "set_only_player_added"
    only: bool


class SetCardTarget(BaseModel):
    type: Literal["set_card_target"] = "set_card_target"
    card_target: int


class SetSongsPerPlayer(BaseModel):
    type: Literal["set_songs_per_player"] = "set_songs_per_player"
    songs_per_player: int


class SetSnippetDuration(BaseModel):
    type: Literal["set_snippet_duration"] = "set_snippet_duration"
    seconds: int


class SetPlacingSeconds(BaseModel):
    type: Literal["set_placing_seconds"] = "set_placing_seconds"
    seconds: int


class SetStealSeconds(BaseModel):
    type: Literal["set_steal_seconds"] = "set_steal_seconds"
    seconds: int


class SetStartingCards(BaseModel):
    type: Literal["set_starting_cards"] = "set_starting_cards"
    count: int


class SetAudioMode(BaseModel):
    type: Literal["set_audio_mode"] = "set_audio_mode"
    mode: AudioMode


class SetStealEnabled(BaseModel):
    type: Literal["set_steal_enabled"] = "set_steal_enabled"
    enabled: bool


class StealPlace(BaseModel):
    # a non-active player races to place the mystery card on their own timeline
    type: Literal["steal_place"] = "steal_place"
    slot_index: int


class SetGameMode(BaseModel):
    type: Literal["set_game_mode"] = "set_game_mode"
    mode: GameMode


class SetBingoCategories(BaseModel):
    # exactly 5 distinct category ids; the ORDER assigns the board colours
    type: Literal["set_bingo_categories"] = "set_bingo_categories"
    categories: list[str]


class SetBingoAnswerSeconds(BaseModel):
    type: Literal["set_bingo_answer_seconds"] = "set_bingo_answer_seconds"
    seconds: int


class BingoAnswer(BaseModel):
    # this round's answer; resubmitting overwrites until the deadline
    type: Literal["bingo_answer"] = "bingo_answer"
    value: str


class BingoMark(BaseModel):
    # a correct player marks one cell of the drawn colour on their own card
    type: Literal["bingo_mark"] = "bingo_mark"
    cell: int


class BingoErase(BaseModel):
    # exact-year bonus: erase one opponent mark (target_id None = pass on it)
    type: Literal["bingo_erase"] = "bingo_erase"
    target_id: str | None = None
    cell: int | None = None


class SetPromo(BaseModel):
    # easter egg: an owner-triggered "ads" overlay shown to everyone else
    type: Literal["set_promo"] = "set_promo"
    active: bool


class PlaceSong(BaseModel):
    type: Literal["place_song"] = "place_song"
    slot_index: int


class AddSong(BaseModel):
    type: Literal["add_song"] = "add_song"
    track_id: str  # raw iTunes track id from the search result


class RemoveSong(BaseModel):
    type: Literal["remove_song"] = "remove_song"
    track_id: str  # raw iTunes track id


class SetSongCategory(BaseModel):
    # correct the auto-detected category of one of your own added songs
    type: Literal["set_song_category"] = "set_song_category"
    track_id: str  # raw iTunes track id
    category: str  # "music" | "film_tv"


class AddBot(BaseModel):
    type: Literal["add_bot"] = "add_bot"
    difficulty: str = "medium"  # "easy" | "medium" | "hard"


class KickPlayer(BaseModel):
    type: Literal["kick_player"] = "kick_player"
    target_id: str


class GiveCard(BaseModel):
    type: Literal["give_card"] = "give_card"
    target_id: str


class TakeCard(BaseModel):
    type: Literal["take_card"] = "take_card"
    target_id: str


class AbortToLobby(BaseModel):
    type: Literal["abort_to_lobby"] = "abort_to_lobby"


class EndGame(BaseModel):
    type: Literal["end_game"] = "end_game"


class Rematch(BaseModel):
    type: Literal["rematch"] = "rematch"


ClientMessage = Annotated[
    Union[
        Join,
        StartRound,
        SetCategoryFilter,
        SetOnlyPlayerAdded,
        SetCardTarget,
        SetSongsPerPlayer,
        SetSnippetDuration,
        SetPlacingSeconds,
        SetStealSeconds,
        SetStartingCards,
        SetAudioMode,
        SetStealEnabled,
        SetAvatar,
        SetGameMode,
        SetBingoCategories,
        SetBingoAnswerSeconds,
        BingoAnswer,
        BingoMark,
        BingoErase,
        SetPromo,
        PlaceSong,
        StealPlace,
        AddSong,
        RemoveSong,
        SetSongCategory,
        AddBot,
        KickPlayer,
        GiveCard,
        TakeCard,
        AbortToLobby,
        EndGame,
        Rematch,
    ],
    Field(discriminator="type"),
]


# ---------- server -> client ----------


class ExtraTrackSummary(BaseModel):
    track_id: str  # raw iTunes track id
    title: str
    artist: str
    category: str = "music"  # "music" | "film_tv" (auto-detected)
    preview_url: str = ""  # for the lobby "listen before/after adding" button


class CardSnapshot(BaseModel):
    track_id: str
    title: str
    artist: str
    year: int
    artwork_url: str | None
    added_by: str | None


class PlacementResult(BaseModel):
    type: Literal["placement_result"] = "placement_result"
    placer_id: str
    slot_index: int | None  # None on timeout
    correct: bool
    card: CardSnapshot
    placer_new_hand: list[CardSnapshot]
    card_counts: dict[str, int]
    placer_finished_place: int | None  # podium place just locked in, if any
    finished_players: list[str]  # finish order so far
    game_finished: bool  # podium complete — game can only be ended
    pool_exhausted: bool  # no fresh tracks left — game can only be ended
    # steal outcome — when the active player missed and a steal phase ran:
    steal_offered: bool = False  # a steal race happened this turn
    stolen_by: str | None = None  # player who stole the card (None = nobody)
    stealer_new_hand: list[CardSnapshot] | None = None  # winner's hand after
    stealer_finished_place: int | None = None  # winner's podium place, if any


class BingoPlayerResult(BaseModel):
    player_id: str
    answer: str  # raw answer as given ("" = none)
    correct: bool
    exact: bool  # exact year on a ±N category → may erase an opponent mark


class BingoRoundResult(BaseModel):
    type: Literal["bingo_round_result"] = "bingo_round_result"
    round: int
    category_index: int
    card: CardSnapshot  # the resolved track (title/artist/year now public)
    results: list[BingoPlayerResult]
    mark_deadline_ms: int | None  # None = nobody has anything to mark/erase
    mark_pending: list[str]
    erase_pending: list[str]


class RoomSnapshot(BaseModel):
    state: RoomState
    players: list[Player]
    host_id: str | None
    cumulative_scores: dict[str, int]
    disconnected: list[str] = []
    category_filter: list[str]
    available_categories: list[str]
    category_counts: dict[str, int]
    extra_tracks_total: int
    per_player_cap: int
    effective_pool_size: int
    your_extra_tracks: list[ExtraTrackSummary]
    only_player_added: bool
    card_target: int
    audio_mode: AudioMode = "online"
    steal_enabled: bool = True
    # host-tunable round settings (always present, also shown in the lobby)
    snippet_duration_s: int = 15
    placing_seconds: int = 30
    steal_seconds: int = 12
    starting_cards: int = 1
    hands: dict[str, list[CardSnapshot]]
    turn_order: list[str]
    finished_players: list[str]
    current_turn_player_id: str | None
    last_placement_result: PlacementResult | None = None
    current_preview_url: str | None = None
    placing_deadline_ms: int | None = None
    # steal phase (only set while state == "hitster_stealing")
    steal_placer_id: str | None = None  # who missed
    steal_deadline_ms: int | None = None
    steal_attempted: list[str] = []  # stealers already out (placed wrong)
    # bingo mode — settings always present, game fields only mid-bingo-game
    game_mode: GameMode = "classic"
    bingo_categories: list[str] = []
    bingo_answer_seconds: int = 25
    bingo_cards: dict[str, list[int]] = {}
    bingo_marks: dict[str, list[int]] = {}
    bingo_round: int = 0
    bingo_category_index: int | None = None
    # last round's (already revealed) song — the Zeitduell/vs_prev pivot
    bingo_prev_title: str | None = None
    bingo_prev_year: int | None = None
    bingo_deadline_ms: int | None = None  # answering OR marking deadline
    bingo_answered: list[str] = []
    bingo_mark_pending: list[str] = []
    bingo_erase_pending: list[str] = []
    last_bingo_result: BingoRoundResult | None = None
    bingo_winners: list[str] = []
    promo_active: bool = False
    promo_by: str | None = None


class Joined(BaseModel):
    type: Literal["joined"] = "joined"
    player_id: str
    room_code: str
    snapshot: RoomSnapshot


class PlayerJoined(BaseModel):
    type: Literal["player_joined"] = "player_joined"
    player: Player


class AvatarChanged(BaseModel):
    type: Literal["avatar_changed"] = "avatar_changed"
    player_id: str
    avatar: str


class PlayerLeft(BaseModel):
    type: Literal["player_left"] = "player_left"
    player_id: str


class HostChanged(BaseModel):
    type: Literal["host_changed"] = "host_changed"
    host_id: str


class PlayerKicked(BaseModel):
    # broadcast when the host removes a player; the kicked client leaves the room
    type: Literal["player_kicked"] = "player_kicked"
    player_id: str


class CardsAdjusted(BaseModel):
    # broadcast when the host gives/takes a card from a player mid-game
    type: Literal["cards_adjusted"] = "cards_adjusted"
    player_id: str
    hand: list[CardSnapshot]
    card_counts: dict[str, int]


class ConnectionChanged(BaseModel):
    # broadcast when a player goes offline (disconnect) or back online; the
    # roster keeps them, just flagged. host_id may shift to a connected player.
    type: Literal["connection_changed"] = "connection_changed"
    disconnected: list[str]
    host_id: str | None


class PlacingPhase(BaseModel):
    type: Literal["placing_phase"] = "placing_phase"
    deadline_ms: int


class CategoryFilterChanged(BaseModel):
    type: Literal["category_filter_changed"] = "category_filter_changed"
    categories: list[str]


class OnlyPlayerAddedChanged(BaseModel):
    type: Literal["only_player_added_changed"] = "only_player_added_changed"
    only: bool


class CardTargetChanged(BaseModel):
    type: Literal["card_target_changed"] = "card_target_changed"
    card_target: int


class RoundSettingsChanged(BaseModel):
    # host-tunable round timing + starting hand (one message for all four)
    type: Literal["round_settings_changed"] = "round_settings_changed"
    snippet_duration_s: int
    placing_seconds: int
    steal_seconds: int
    starting_cards: int


class AudioModeChanged(BaseModel):
    type: Literal["audio_mode_changed"] = "audio_mode_changed"
    mode: AudioMode


class StealEnabledChanged(BaseModel):
    type: Literal["steal_enabled_changed"] = "steal_enabled_changed"
    enabled: bool


class StealStarted(BaseModel):
    # the active player missed; eligible players race to place it themselves
    type: Literal["steal_started"] = "steal_started"
    placer_id: str  # who missed (shown to all; the year stays hidden)
    deadline_ms: int


class StealAttempted(BaseModel):
    # a stealer locked in a (wrong) placement and is now out of the race
    type: Literal["steal_attempted"] = "steal_attempted"
    player_id: str


class GameModeChanged(BaseModel):
    type: Literal["game_mode_changed"] = "game_mode_changed"
    mode: GameMode


class BingoSettingsChanged(BaseModel):
    type: Literal["bingo_settings_changed"] = "bingo_settings_changed"
    categories: list[str]  # 5 ids, order = board colour slots
    answer_seconds: int


class BingoGameStarted(BaseModel):
    # cards are public knowledge (like the physical table): player -> 25 cells,
    # each holding a colour slot 0..4 (slot i = i-th entry of `categories`)
    type: Literal["bingo_game_started"] = "bingo_game_started"
    participants: list[str]
    cards: dict[str, list[int]]
    categories: list[str]


class BingoSpin(BaseModel):
    # the disco-ball wheel picks this round's category; the song follows after
    # the spin animation (BingoAnswering)
    type: Literal["bingo_spin"] = "bingo_spin"
    round: int
    category_index: int  # 0..4 into the room's categories
    # last round's revealed song — prompt data for the vs_prev category
    prev_title: str | None = None
    prev_year: int | None = None


class BingoAnswering(BaseModel):
    type: Literal["bingo_answering"] = "bingo_answering"
    deadline_ms: int
    preview_url: str


class BingoAnswered(BaseModel):
    # progress ping: who has locked in an answer so far (values stay hidden)
    type: Literal["bingo_answered"] = "bingo_answered"
    player_id: str
    answered: list[str]


class BingoMarksChanged(BaseModel):
    # a mark was placed or erased (player_id = whose card changed); with
    # player_id None only the pending lists changed (someone passed on an erase)
    type: Literal["bingo_marks_changed"] = "bingo_marks_changed"
    player_id: str | None
    marks: list[int] | None
    actor_id: str | None  # who acted (eraser ≠ card owner)
    erased: bool
    card_counts: dict[str, int]  # marks per player (the bingo "score")
    mark_pending: list[str]
    erase_pending: list[str]


class BingoRoundDone(BaseModel):
    # marking resolved (incl. timeout auto-picks); full marks state + winners.
    # winners non-empty → GameOver follows immediately after
    type: Literal["bingo_round_done"] = "bingo_round_done"
    marks: dict[str, list[int]]
    card_counts: dict[str, int]
    winners: list[str]


class HitsterGameStarted(BaseModel):
    type: Literal["hitster_game_started"] = "hitster_game_started"
    turn_order: list[str]
    hands: dict[str, list[CardSnapshot]]


class HitsterTurnChanged(BaseModel):
    type: Literal["hitster_turn_changed"] = "hitster_turn_changed"
    current_turn_player_id: str
    preview_url: str
    snippet_duration_s: int


class ExtraTracksTotalChanged(BaseModel):
    type: Literal["extra_tracks_total_changed"] = "extra_tracks_total_changed"
    extra_tracks_total: int
    per_player_cap: int
    effective_pool_size: int


class YourExtraTracksChanged(BaseModel):
    type: Literal["your_extra_tracks_changed"] = "your_extra_tracks_changed"
    your_extra_tracks: list[ExtraTrackSummary]


class GameOver(BaseModel):
    type: Literal["game_over"] = "game_over"
    cumulative_scores: dict[str, int]
    finished_players: list[str]  # finish order = final podium ranking


class RematchStarted(BaseModel):
    type: Literal["rematch_started"] = "rematch_started"


class PromoState(BaseModel):
    type: Literal["promo_state"] = "promo_state"
    active: bool
    triggered_by: str | None  # player who toggled it — they stay ad-free


class ServerError(BaseModel):
    type: Literal["error"] = "error"
    message: str
