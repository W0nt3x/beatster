import asyncio
from typing import Any

import pytest

from app import room as room_module
from app.catalog import Track
from app.room import Room, RoomError
from app.schemas import (
    AvatarChanged,
    HostChanged,
    PlacementResult,
    PlayerJoined,
    PlayerLeft,
)


class FakeCatalog:
    def __init__(self, tracks: list[Track]) -> None:
        self.tracks = list(tracks)

    def available_categories(self) -> list[str]:
        return sorted({t.category for t in self.tracks})

    def category_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in self.tracks:
            counts[t.category] = counts.get(t.category, 0) + 1
        return counts

    def has_seed_track(self, track_id: str) -> bool:
        return any(t.id == track_id for t in self.tracks)


@pytest.fixture
def fake_catalog() -> FakeCatalog:
    return FakeCatalog(
        [
            Track(id="a", title="A", artist="X", year=1985, preview_url="http://a"),
            Track(id="b", title="B", artist="Y", year=2000, preview_url="http://b"),
            Track(id="c", title="C", artist="Z", year=2010, preview_url="http://c"),
        ]
    )


@pytest.fixture(autouse=True)
def _no_community_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    # don't touch the real community_tracks.json from room tests
    monkeypatch.setattr(room_module, "remember_community_track", lambda _t: None)


@pytest.fixture(autouse=True)
def _no_stats_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    # don't touch the real hitster.db from room tests
    monkeypatch.setattr(room_module, "record_game_result", lambda **_kw: None)
    monkeypatch.setattr(room_module, "record_placement", lambda **_kw: None)
    monkeypatch.setattr(room_module, "record_activity", lambda *_a, **_kw: None)


@pytest.fixture
def fast_timers(monkeypatch: pytest.MonkeyPatch) -> None:
    # snippet + intro fire on the next loop tick; placing timeout effectively
    # never (cancelled by tests)
    monkeypatch.setattr(room_module, "SNIPPET_DURATION_S", 0)
    monkeypatch.setattr(room_module, "PLACING_TIMEOUT_S", 60)
    monkeypatch.setattr(room_module, "HITSTER_INTRO_DURATION_S", 0)


@pytest.fixture
def broadcasts() -> list[Any]:
    return []


@pytest.fixture
def destroyed() -> list[bool]:
    return []


@pytest.fixture
def room(fake_catalog: FakeCatalog, broadcasts: list[Any], destroyed: list[bool]) -> Room:
    async def broadcast(msg: Any) -> None:
        broadcasts.append(msg)

    async def on_empty() -> None:
        destroyed.append(True)

    return Room(
        code="TEST",
        catalog=fake_catalog,  # type: ignore[arg-type]
        broadcast=broadcast,
        on_empty=on_empty,
    )


class _TrackQueue:
    """Returns predetermined tracks in order. None signals exhaustion."""

    def __init__(self, tracks: list[Track]) -> None:
        self.tracks = list(tracks)
        self.idx = 0

    def pop(self) -> tuple[Track, None, None] | None:
        if self.idx >= len(self.tracks):
            return None
        t = self.tracks[self.idx]
        self.idx += 1
        return (t, None, None)


def _patch_picker(
    monkeypatch: pytest.MonkeyPatch, tracks: list[Track]
) -> None:
    """Make _pick_track_no_recycle return tracks in order; preserve player order."""
    queue = _TrackQueue(tracks)
    monkeypatch.setattr(
        room_module.Room, "_pick_track_no_recycle", lambda self: queue.pop()
    )
    monkeypatch.setattr(room_module.random, "shuffle", lambda lst: None)
    # also force _eligible_pool_size to be plenty so the pre-flight passes
    monkeypatch.setattr(
        room_module.Room, "_eligible_pool_size", lambda self: len(tracks)
    )


# ---------- lobby / lifecycle ----------


async def test_first_player_is_host(room: Room) -> None:
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    assert room.host_id == p1.id
    assert [p.name for p in room.players] == ["Alice", "Bob"]
    assert p2.id != p1.id


async def test_avatar_join_set_and_validation(
    room: Room, broadcasts: list[Any]
) -> None:
    p1 = await room.add_player("Alice", None, avatar="fun-emoji:abc123")
    assert p1.avatar == "fun-emoji:abc123"

    # garbage avatar strings are silently dropped, not stored
    p2 = await room.add_player("Bob", None, avatar="<script>:x")
    assert p2.avatar == ""

    # explicit change broadcasts to everyone
    await room.set_avatar(p2.id, "thumbs:XY_z-9")
    assert room.players[1].avatar == "thumbs:XY_z-9"
    changed = [m for m in broadcasts if isinstance(m, AvatarChanged)]
    assert changed and changed[-1].player_id == p2.id
    assert changed[-1].avatar == "thumbs:XY_z-9"

    # invalid avatar on set is a RoomError
    with pytest.raises(RoomError):
        await room.set_avatar(p2.id, "not valid!!")

    # a rejoin with a stored preference wins over the server value
    await room.add_player("Bob", p2.id, avatar="adventurer-neutral:q1")
    assert room.players[1].avatar == "adventurer-neutral:q1"

    # persistence roundtrip keeps avatars
    data = room.to_persist()
    assert data["players"][0]["avatar"] == "fun-emoji:abc123"


async def test_rejoin_with_same_player_id_does_not_duplicate(room: Room, broadcasts: list[Any]) -> None:
    p1 = await room.add_player("Alice", None)
    broadcasts.clear()
    p1_again = await room.add_player("Alice", p1.id)
    assert p1_again.id == p1.id
    assert len(room.players) == 1
    assert not [m for m in broadcasts if isinstance(m, PlayerJoined)]


async def test_only_host_can_start_game(
    room: Room, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracks = [
        Track(id=f"t{i}", title=f"T{i}", artist="A", year=1980 + i, preview_url=f"http://t{i}")
        for i in range(5)
    ]
    _patch_picker(monkeypatch, tracks)

    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    with pytest.raises(RoomError, match="only the host"):
        await room.start_round(p2.id)
    # host can
    await room.start_round(p1.id)
    assert room.state == "hitster_intro"
    room._cancel_timers()


async def test_host_transfers_when_host_leaves(
    room: Room, broadcasts: list[Any]
) -> None:
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    broadcasts.clear()

    await room.remove_player(p1.id)
    assert room.host_id == p2.id
    assert any(
        isinstance(m, HostChanged) and m.host_id == p2.id for m in broadcasts
    )
    assert any(
        isinstance(m, PlayerLeft) and m.player_id == p1.id for m in broadcasts
    )


async def test_host_can_kick_player(room: Room, broadcasts: list[Any]) -> None:
    from app.schemas import PlayerKicked

    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    p3 = await room.add_player("Carol", None)
    broadcasts.clear()

    await room.kick_player(p1.id, p2.id)
    assert not room.has_player(p2.id)
    assert room.has_player(p1.id) and room.has_player(p3.id)
    assert any(
        isinstance(m, PlayerKicked) and m.player_id == p2.id for m in broadcasts
    )
    assert any(
        isinstance(m, PlayerLeft) and m.player_id == p2.id for m in broadcasts
    )


async def test_kick_rejects_non_host_self_and_unknown(room: Room) -> None:
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    with pytest.raises(RoomError, match="only the host"):
        await room.kick_player(p2.id, p1.id)
    with pytest.raises(RoomError, match="cannot kick themselves"):
        await room.kick_player(p1.id, p1.id)
    with pytest.raises(RoomError, match="no such player"):
        await room.kick_player(p1.id, "ghost")


async def test_room_destroyed_when_last_player_leaves(
    room: Room, destroyed: list[bool]
) -> None:
    p1 = await room.add_player("Alice", None)
    await room.remove_player(p1.id)
    assert destroyed == [True]


async def test_rematch_only_in_game_over(room: Room) -> None:
    p1 = await room.add_player("Alice", None)
    with pytest.raises(RoomError, match="cannot rematch"):
        await room.rematch(p1.id)


# ---------- settings ----------


async def test_set_card_target_range(room: Room) -> None:
    p1 = await room.add_player("Alice", None)
    await room.set_card_target(p1.id, 5)
    assert room.card_target == 5
    with pytest.raises(RoomError, match="between"):
        await room.set_card_target(p1.id, 1)
    with pytest.raises(RoomError, match="between"):
        await room.set_card_target(p1.id, 999)


async def test_only_host_can_set_card_target(room: Room) -> None:
    await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    with pytest.raises(RoomError, match="only the host"):
        await room.set_card_target(p2.id, 5)


async def test_set_audio_mode_host_only(
    room: Room, broadcasts: list[Any]
) -> None:
    from app.schemas import AudioModeChanged

    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    assert room.audio_mode == "online"  # default
    # only the host may change it
    with pytest.raises(RoomError, match="only the host"):
        await room.set_audio_mode(p2.id, "couch")

    broadcasts.clear()
    await room.set_audio_mode(p1.id, "couch")
    assert room.audio_mode == "couch"
    assert any(
        isinstance(m, AudioModeChanged) and m.mode == "couch" for m in broadcasts
    )
    assert room.snapshot_for(p1.id).audio_mode == "couch"


# ---------- player-added songs ----------


async def test_per_player_cap_defaults_and_is_independent_of_card_target(
    room: Room,
) -> None:
    p1 = await room.add_player("Alice", None)
    # cap defaults to DEFAULT_SONGS_PER_PLAYER, unaffected by the card target
    assert room.per_player_cap == 10
    await room.set_card_target(p1.id, 7)
    assert room.per_player_cap == 10


async def test_set_songs_per_player(room: Room) -> None:
    p1 = await room.add_player("Alice", None)
    await room.set_songs_per_player(p1.id, 3)
    assert room.per_player_cap == 3
    # zero is valid (disables contributions)
    await room.set_songs_per_player(p1.id, 0)
    assert room.per_player_cap == 0
    with pytest.raises(RoomError, match="between"):
        await room.set_songs_per_player(p1.id, 21)


async def test_only_host_can_set_songs_per_player(room: Room) -> None:
    await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    with pytest.raises(RoomError, match="only the host"):
        await room.set_songs_per_player(p2.id, 5)


async def test_set_promo_broadcasts_and_persists_in_snapshot(
    room: Room, broadcasts: list[Any]
) -> None:
    from app.schemas import PromoState

    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    broadcasts.clear()

    # anyone may toggle it (no host check) — the triggerer is recorded
    await room.set_promo(p2.id, True)
    assert room.promo_active is True
    assert room.promo_by == p2.id
    msg = next(m for m in broadcasts if isinstance(m, PromoState))
    assert msg.active is True and msg.triggered_by == p2.id
    # both players' snapshots carry the state; clients decide who's ad-free
    assert room.snapshot_for(p1.id).promo_active is True
    assert room.snapshot_for(p1.id).promo_by == p2.id

    await room.set_promo(p2.id, False)
    assert room.promo_active is False
    assert room.promo_by is None
    assert room.snapshot_for(p1.id).promo_active is False


async def test_add_song_stores_track_and_returns_summary(
    room: Room,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_track = Track(
        id="itunes_99",
        title="Fake",
        artist="FakeArtist",
        year=1990,
        preview_url="http://fake",
    )

    async def fake_lookup(track_id: str) -> Track | None:
        return fake_track if track_id == "99" else None

    monkeypatch.setattr(room_module, "itunes_lookup_track", fake_lookup)

    p1 = await room.add_player("Alice", None)
    your_list = await room.add_song(p1.id, "99")
    assert len(your_list) == 1
    assert your_list[0].track_id == "99"
    assert your_list[0].title == "Fake"
    assert your_list[0].artist == "FakeArtist"
    assert "itunes_99" in room.extra_tracks
    assert room.extra_tracks["itunes_99"].added_by_id == p1.id
    assert room.extra_tracks["itunes_99"].added_by_name == "Alice"


async def test_add_song_rejects_over_cap(
    room: Room, monkeypatch: pytest.MonkeyPatch
) -> None:
    counter = {"n": 0}

    async def fake_lookup(track_id: str) -> Track | None:
        counter["n"] += 1
        return Track(
            id=f"itunes_{track_id}",
            title=f"T{counter['n']}",
            artist="A",
            year=1990,
            preview_url=f"http://t{track_id}",
        )

    monkeypatch.setattr(room_module, "itunes_lookup_track", fake_lookup)

    p1 = await room.add_player("Alice", None)
    await room.set_songs_per_player(p1.id, 2)
    for i in range(2):
        await room.add_song(p1.id, str(100 + i))
    with pytest.raises(RoomError, match="reached your song limit"):
        await room.add_song(p1.id, "999")


async def test_add_song_rejects_duplicate(
    room: Room, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_lookup(track_id: str) -> Track | None:
        return Track(
            id=f"itunes_{track_id}",
            title="Dup",
            artist="A",
            year=1990,
            preview_url="http://x",
        )

    monkeypatch.setattr(room_module, "itunes_lookup_track", fake_lookup)
    p1 = await room.add_player("Alice", None)
    await room.add_song(p1.id, "55")
    with pytest.raises(RoomError, match="already in the pool"):
        await room.add_song(p1.id, "55")


async def test_add_song_rejects_when_lookup_fails(
    room: Room, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_lookup(track_id: str) -> Track | None:
        return None

    monkeypatch.setattr(room_module, "itunes_lookup_track", fake_lookup)
    p1 = await room.add_player("Alice", None)
    with pytest.raises(RoomError, match="iTunes"):
        await room.add_song(p1.id, "1")


async def test_remove_song_only_own_contribution(
    room: Room, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_lookup(track_id: str) -> Track | None:
        return Track(
            id=f"itunes_{track_id}",
            title="X",
            artist="A",
            year=1990,
            preview_url="http://x",
        )

    monkeypatch.setattr(room_module, "itunes_lookup_track", fake_lookup)
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    await room.add_song(p1.id, "11")
    # Bob can't remove Alice's
    with pytest.raises(RoomError, match="not found in your contributions"):
        await room.remove_song(p2.id, "11")
    # Alice can
    your_list = await room.remove_song(p1.id, "11")
    assert your_list == []
    assert "itunes_11" not in room.extra_tracks


async def test_only_player_added_excludes_seed_catalog(
    room: Room, monkeypatch: pytest.MonkeyPatch
) -> None:
    # with only-player-added on and no contributions, the seed catalog is
    # excluded → the pool is empty
    p1 = await room.add_player("Alice", None)
    await room.set_only_player_added(p1.id, True)
    assert room._pick_track_no_recycle() is None


async def test_only_player_added_picks_extras(
    room: Room, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_lookup(track_id: str) -> Track | None:
        return Track(
            id=f"itunes_{track_id}",
            title="Mine",
            artist="A",
            year=1995,
            preview_url="http://m",
        )

    monkeypatch.setattr(room_module, "itunes_lookup_track", fake_lookup)

    p1 = await room.add_player("Alice", None)
    await room.add_song(p1.id, "42")
    await room.set_only_player_added(p1.id, True)
    pick = room._pick_track_no_recycle()
    assert pick is not None
    track, _, _ = pick
    assert track.id == "itunes_42"


async def test_only_player_added_only_host_can_toggle(room: Room) -> None:
    await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    with pytest.raises(RoomError, match="only the host"):
        await room.set_only_player_added(p2.id, True)


# ---------- gameplay ----------


async def test_start_requires_enough_pool(
    room: Room, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        room_module.Room, "_eligible_pool_size", lambda self: 2
    )
    p1 = await room.add_player("Alice", None)
    await room.add_player("Bob", None)
    # 2 players need 3 tracks (2 starting + 1 mystery), only 2 available
    with pytest.raises(RoomError, match="need at least 3 tracks"):
        await room.start_round(p1.id)


async def test_start_enters_intro_then_listening(
    room: Room, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Keep snippet long so we don't cascade past listening into placing
    monkeypatch.setattr(room_module, "SNIPPET_DURATION_S", 60)
    monkeypatch.setattr(room_module, "PLACING_TIMEOUT_S", 60)
    monkeypatch.setattr(room_module, "HITSTER_INTRO_DURATION_S", 0)

    tracks = [
        Track(id=f"t{i}", title=f"T{i}", artist="A", year=1980 + i, preview_url=f"http://t{i}")
        for i in range(5)
    ]
    _patch_picker(monkeypatch, tracks)

    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    await room.start_round(p1.id)

    # intro fires first
    assert room.state == "hitster_intro"
    assert len(room.hands[p1.id]) == 1
    assert len(room.hands[p2.id]) == 1
    assert set(room.turn_order) == {p1.id, p2.id}
    assert room.hands[p1.id][0].year == 1980
    assert room.hands[p2.id][0].year == 1981
    assert room.current_track is not None
    assert room.current_track.year == 1982

    await asyncio.sleep(0.05)  # let intro_task fire
    assert room.state == "hitster_listening"
    room._cancel_timers()


async def test_intro_duration_holds_snippet(
    room: Room, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(room_module, "HITSTER_INTRO_DURATION_S", 0.05)
    monkeypatch.setattr(room_module, "SNIPPET_DURATION_S", 60)
    monkeypatch.setattr(room_module, "PLACING_TIMEOUT_S", 60)

    tracks = [
        Track(id=f"t{i}", title=f"T{i}", artist="A", year=1980 + i, preview_url=f"http://t{i}")
        for i in range(3)
    ]
    _patch_picker(monkeypatch, tracks)

    p1 = await room.add_player("Alice", None)
    await room.start_round(p1.id)

    # immediately after start: in intro
    assert room.state == "hitster_intro"

    # before intro elapses
    await asyncio.sleep(0.02)
    assert room.state == "hitster_intro"

    # after intro elapses
    await asyncio.sleep(0.1)
    assert room.state == "hitster_listening"
    room._cancel_timers()


async def test_correct_placement_grows_hand(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None
) -> None:
    # p1: 1980, p2: 1981, mystery: 1990 → correct after p1's 1980 (slot 1)
    tracks = [
        Track(id="t1", title="A", artist="A", year=1980, preview_url="http://t1"),
        Track(id="t2", title="B", artist="A", year=1981, preview_url="http://t2"),
        Track(id="t3", title="C", artist="A", year=1990, preview_url="http://t3"),
    ]
    _patch_picker(monkeypatch, tracks)

    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)
    assert room.state == "hitster_placing"
    assert room.current_turn_player_id == p1.id

    await room.place_song(p1.id, 1)  # after 1980
    assert room.state == "hitster_reveal"
    assert room.last_placement_result is not None
    assert room.last_placement_result.correct is True
    assert len(room.hands[p1.id]) == 2
    assert room.cumulative_scores[p1.id] == 2

    # non-host (or non-target) check via card_counts
    assert room.last_placement_result.card_counts[p1.id] == 2
    assert room.last_placement_result.card_counts[p2.id] == 1


async def test_leave_and_rejoin_mid_game_keeps_hand_and_score(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None
) -> None:
    # An accidental disconnect must not cost a player their cards: mid-game they
    # go "offline" (kept in the roster, hand + slot intact, skipped in the
    # rotation), and reconnecting brings them back online with their cards.
    tracks = [
        Track(id="t1", title="A", artist="A", year=1980, preview_url="http://t1"),
        Track(id="t2", title="B", artist="A", year=1981, preview_url="http://t2"),
        Track(id="t3", title="C", artist="A", year=1982, preview_url="http://t3"),
        Track(id="t4", title="D", artist="A", year=1990, preview_url="http://t4"),
    ]
    _patch_picker(monkeypatch, tracks)

    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    p3 = await room.add_player("Carol", None)
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)
    await room.place_song(p1.id, 1)  # after 1980 → correct, Alice now has 2 cards
    assert len(room.hands[p1.id]) == 2

    # Alice drops (grace expired → remove_player) → offline, not removed
    await room.remove_player(p1.id)
    assert room.has_player(p1.id)              # still in the roster
    assert p1.id in room.disconnected          # but flagged offline
    assert p1.id in room.turn_order            # keeps her slot
    assert len(room.hands[p1.id]) == 2         # cards preserved
    # host migrates to a connected player while she's away
    assert room.host_id == p2.id

    # Alice reconnects with the same id → back online
    p1_back = await room.add_player("Alice", p1.id)
    assert p1_back.id == p1.id
    assert p1.id not in room.disconnected
    assert len(room.hands[p1.id]) == 2
    assert room.cumulative_scores[p1.id] == 2
    assert room.host_id == p1.id               # host returns to her
    assert p1.id not in room.snapshot_for(p1.id).disconnected


async def test_wrong_placement_no_card(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None
) -> None:
    # p1: 1980, p2: 1981, mystery: 1990 → wrong if p1 places at slot 0 (before 1980)
    tracks = [
        Track(id="t1", title="A", artist="A", year=1980, preview_url="http://t1"),
        Track(id="t2", title="B", artist="A", year=1981, preview_url="http://t2"),
        Track(id="t3", title="C", artist="A", year=1990, preview_url="http://t3"),
    ]
    _patch_picker(monkeypatch, tracks)

    p1 = await room.add_player("Alice", None)
    await room.add_player("Bob", None)
    room.steal_enabled = False  # isolate the plain wrong-placement reveal
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)

    await room.place_song(p1.id, 0)  # before 1980 → wrong
    assert room.last_placement_result is not None
    assert room.last_placement_result.correct is False
    assert len(room.hands[p1.id]) == 1
    assert room.cumulative_scores[p1.id] == 1


async def test_only_active_player_can_place(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None
) -> None:
    tracks = [
        Track(id=f"t{i}", title=f"T{i}", artist="A", year=1980 + i, preview_url=f"http://t{i}")
        for i in range(3)
    ]
    _patch_picker(monkeypatch, tracks)

    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)

    # active is p1; p2 tries to place
    with pytest.raises(RoomError, match="not your turn"):
        await room.place_song(p2.id, 0)


async def test_target_hit_then_end_game(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None
) -> None:
    # 1 player, target=2: starting card + 1 correct placement → finished
    tracks = [
        Track(id="t1", title="A", artist="A", year=1980, preview_url="http://t1"),
        Track(id="t2", title="B", artist="A", year=1990, preview_url="http://t2"),
    ]
    _patch_picker(monkeypatch, tracks)

    p1 = await room.add_player("Alice", None)
    await room.set_card_target(p1.id, 2)
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)

    await room.place_song(p1.id, 1)  # after 1980 → correct, now 2 cards
    result = room.last_placement_result
    assert result is not None
    assert result.placer_finished_place == 1
    assert result.game_finished is True
    assert room.finished_players == [p1.id]

    await room.end_game(p1.id)
    assert room.state == "game_over"


async def test_next_turn_after_podium_complete_auto_ends(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None
) -> None:
    # a stale client sending start_round after the podium is complete gets
    # the scoreboard instead of an error
    tracks = [
        Track(id="t1", title="A", artist="A", year=1980, preview_url="http://t1"),
        Track(id="t2", title="B", artist="A", year=1990, preview_url="http://t2"),
    ]
    _patch_picker(monkeypatch, tracks)

    p1 = await room.add_player("Alice", None)
    await room.set_card_target(p1.id, 2)
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)
    await room.place_song(p1.id, 1)

    await room.start_round(p1.id)
    assert room.state == "game_over"


async def test_podium_places_by_player_count(room: Room) -> None:
    room.turn_order = ["a", "b"]
    assert room._podium_places() == 1
    room.turn_order = ["a", "b", "c"]
    assert room._podium_places() == 2
    room.turn_order = ["a", "b", "c", "d"]
    assert room._podium_places() == 3
    room.turn_order = ["a", "b", "c", "d", "e"]
    assert room._podium_places() == 3


async def test_three_player_game_plays_on_for_second_place(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None
) -> None:
    # 3 players → places 1+2 are played for; the finisher leaves the
    # rotation, and the game ends once place 2 is decided
    tracks = [
        Track(id="s1", title="S1", artist="A", year=1980, preview_url="http://s1"),
        Track(id="s2", title="S2", artist="A", year=1981, preview_url="http://s2"),
        Track(id="s3", title="S3", artist="A", year=1982, preview_url="http://s3"),
    ] + [
        Track(id=f"m{i}", title=f"M{i}", artist="A", year=1990, preview_url=f"http://m{i}")
        for i in range(1, 5)
    ]
    _patch_picker(monkeypatch, tracks)

    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    p3 = await room.add_player("Carla", None)
    await room.set_card_target(p1.id, 2)
    room.steal_enabled = False  # isolate podium mechanics from the steal phase

    await room.start_round(p1.id)
    await asyncio.sleep(0.05)
    # Alice places correctly → finishes as place 1; game continues
    await room.place_song(p1.id, 1)
    result = room.last_placement_result
    assert result is not None
    assert result.placer_finished_place == 1
    assert result.game_finished is False
    with pytest.raises(RoomError, match="podium not decided"):
        await room.end_game(p1.id)

    # Bob and Carla each place wrong
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)
    assert room.current_turn_player_id == p2.id
    await room.place_song(p2.id, 0)  # before 1981 → wrong for 1990

    await room.start_round(p1.id)
    await asyncio.sleep(0.05)
    assert room.current_turn_player_id == p3.id
    await room.place_song(p3.id, 0)

    # rotation skips the finished Alice and returns to Bob
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)
    assert room.current_turn_player_id == p2.id

    # Bob places correctly → place 2 → podium complete
    await room.place_song(p2.id, 1)
    result = room.last_placement_result
    assert result is not None
    assert result.placer_finished_place == 2
    assert result.game_finished is True

    await room.end_game(p1.id)
    assert room.state == "game_over"
    assert room.finished_players == [p1.id, p2.id]


async def test_podium_completes_when_contenders_run_out(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None
) -> None:
    # 3 players → 2 places, but one contender leaves after place 1 is
    # decided: only one contender remains, so the game is over
    tracks = [
        Track(id="s1", title="S1", artist="A", year=1980, preview_url="http://s1"),
        Track(id="s2", title="S2", artist="A", year=1981, preview_url="http://s2"),
        Track(id="s3", title="S3", artist="A", year=1982, preview_url="http://s3"),
        Track(id="m1", title="M1", artist="A", year=1990, preview_url="http://m1"),
    ]
    _patch_picker(monkeypatch, tracks)

    p1 = await room.add_player("Alice", None)
    await room.add_player("Bob", None)
    p3 = await room.add_player("Carla", None)
    await room.set_card_target(p1.id, 2)

    await room.start_round(p1.id)
    await asyncio.sleep(0.05)
    await room.place_song(p1.id, 1)
    assert room.last_placement_result is not None
    assert room.last_placement_result.game_finished is False

    # a contender is fully removed (kicked) → only one contender remains
    await room.kick_player(p1.id, p3.id)
    await room.end_game(p1.id)
    assert room.state == "game_over"


async def test_contributor_can_win_own_song(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None
) -> None:
    # Alice contributes a 1990 song; mystery = her song; correct placement
    # counts normally (the old "contributor can't win" rule was removed
    # 2026-06-13 by design decision — friend-group trust over anti-cheat).
    async def fake_lookup(track_id: str) -> Track | None:
        return Track(
            id=f"itunes_{track_id}",
            title="Mine",
            artist="A",
            year=1990,
            preview_url="http://m",
        )

    monkeypatch.setattr(room_module, "itunes_lookup_track", fake_lookup)

    p1 = await room.add_player("Alice", None)
    await room.add_player("Bob", None)
    # Alice contributes
    await room.add_song(p1.id, "42")

    # Force the contributed track to be the mystery, with two seed cards as starting
    seed_t1 = Track(id="s1", title="S1", artist="A", year=1980, preview_url="http://s1")
    seed_t2 = Track(id="s2", title="S2", artist="A", year=2000, preview_url="http://s2")
    contributed_t = list(room.extra_tracks.values())[0]
    queue = [
        (seed_t1, None, None),
        (seed_t2, None, None),
        (contributed_t.track, contributed_t.added_by_id, contributed_t.added_by_name),
    ]
    iq = iter(queue)
    monkeypatch.setattr(
        room_module.Room, "_pick_track_no_recycle", lambda self: next(iq, None)
    )
    monkeypatch.setattr(room_module.random, "shuffle", lambda lst: None)
    monkeypatch.setattr(
        room_module.Room, "_eligible_pool_size", lambda self: 3
    )

    await room.start_round(p1.id)
    await asyncio.sleep(0.05)
    # p1 has 1980, mystery is 1990 → slot 1 ("after 1980") is correct
    await room.place_song(p1.id, 1)
    assert room.last_placement_result is not None
    assert room.last_placement_result.correct is True
    assert len(room.hands[p1.id]) == 2


async def test_pool_exhaustion_allows_early_end_game(
    room: Room, fast_timers: None
) -> None:
    # Real picking, no patches: 1 player, 3-track catalog, target far away.
    # Start consumes 2 tracks (starting card + mystery), turn 2 the third —
    # then the pool is dry and the host must be able to end the game early.
    p1 = await room.add_player("Alice", None)

    await room.start_round(p1.id)
    await asyncio.sleep(0.05)  # intro -> listening -> placing (timers at 0)
    assert room.state == "hitster_placing"
    await room.place_song(p1.id, 0)

    result = room.last_placement_result
    assert result is not None
    assert result.pool_exhausted is False  # one fresh track left
    # ending early while tracks remain is still rejected
    with pytest.raises(RoomError, match="tracks remain"):
        await room.end_game(p1.id)

    await room.start_round(p1.id)
    await asyncio.sleep(0.05)
    await room.place_song(p1.id, 0)

    result = room.last_placement_result
    assert result is not None
    assert result.pool_exhausted is True
    assert result.game_finished is False
    # ending the game now works and keeps the scores
    await room.end_game(p1.id)
    assert room.state == "game_over"


async def test_next_turn_with_empty_pool_auto_ends_game(
    room: Room, fast_timers: None, broadcasts: list[Any]
) -> None:
    # A stale client may still send start_round on an exhausted pool — the
    # server ends the game gracefully instead of erroring.
    from app.schemas import GameOver

    p1 = await room.add_player("Alice", None)
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)
    await room.place_song(p1.id, 0)
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)
    await room.place_song(p1.id, 0)  # third track played, pool now dry

    await room.start_round(p1.id)  # "next turn" on empty pool
    assert room.state == "game_over"
    assert any(isinstance(m, GameOver) for m in broadcasts)


async def test_rematch_clears_state(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None
) -> None:
    tracks = [
        Track(id="t1", title="A", artist="A", year=1980, preview_url="http://t1"),
        Track(id="t2", title="B", artist="A", year=1990, preview_url="http://t2"),
    ]
    _patch_picker(monkeypatch, tracks)

    p1 = await room.add_player("Alice", None)
    await room.set_card_target(p1.id, 2)
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)
    await room.place_song(p1.id, 1)
    await room.end_game(p1.id)
    assert room.state == "game_over"

    await room.rematch(p1.id)
    assert room.state == "lobby"
    assert room.hands == {}
    assert room.turn_order == []
    assert room.finished_players == []
    assert room.cumulative_scores[p1.id] == 0
    assert room.played_track_ids == set()
    # card_target persists across rematches
    assert room.card_target == 2


async def test_rematch_prunes_offline_players(
    room: Room, broadcasts: list[Any]
) -> None:
    # a player who is still offline when the next lobby starts would become a
    # ghost in the new turn_order — they're fully removed instead (a rejoin
    # re-adds them cleanly, like any lobby join)
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    room.state = "game_over"
    room.disconnected.add(p2.id)
    broadcasts.clear()

    await room.rematch(p1.id)
    assert room.state == "lobby"
    assert [p.id for p in room.players] == [p1.id]
    assert room.disconnected == set()
    assert [m.player_id for m in broadcasts if isinstance(m, PlayerLeft)] == [
        p2.id
    ]


# ---------- category filter ----------


async def test_category_filter_defaults_to_all_available(
    fake_catalog: FakeCatalog, broadcasts: list[Any], destroyed: list[bool]
) -> None:
    # Inject a film_tv track into the fake catalog
    fake_catalog.tracks.append(
        Track(
            id="ft1",
            title="Theme",
            artist="Composer",
            year=2010,
            preview_url="http://ft",
            category="film_tv",
        )
    )

    async def broadcast(msg: Any) -> None:
        broadcasts.append(msg)

    async def on_empty() -> None:
        destroyed.append(True)

    r = Room(
        code="X",
        catalog=fake_catalog,  # type: ignore[arg-type]
        broadcast=broadcast,
        on_empty=on_empty,
    )
    assert sorted(r.category_filter) == ["film_tv", "music"]


async def test_set_category_filter_validates_and_broadcasts(
    room: Room, broadcasts: list[Any]
) -> None:
    from app.schemas import CategoryFilterChanged

    p1 = await room.add_player("Alice", None)
    broadcasts.clear()

    # default fake catalog only has "music" — adding film_tv to filter must fail
    with pytest.raises(RoomError, match="unknown"):
        await room.set_category_filter(p1.id, ["film_tv"])

    await room.set_category_filter(p1.id, ["music"])
    assert room.category_filter == ["music"]
    assert any(
        isinstance(m, CategoryFilterChanged) and m.categories == ["music"]
        for m in broadcasts
    )


async def test_category_filter_rejects_empty(room: Room) -> None:
    p1 = await room.add_player("Alice", None)
    with pytest.raises(RoomError, match="at least one category"):
        await room.set_category_filter(p1.id, [])


async def test_only_host_can_set_category_filter(room: Room) -> None:
    await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    with pytest.raises(RoomError, match="only the host"):
        await room.set_category_filter(p2.id, ["music"])


async def test_host_give_and_take_card_and_abort(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None
) -> None:
    from app.schemas import CardsAdjusted

    tracks = [
        Track(id="t1", title="A", artist="A", year=1980, preview_url="http://t1"),
        Track(id="t2", title="B", artist="A", year=1981, preview_url="http://t2"),
        Track(id="t3", title="C", artist="A", year=1990, preview_url="http://t3"),
        Track(id="t4", title="D", artist="A", year=1995, preview_url="http://t4"),
        Track(id="t5", title="E", artist="A", year=2001, preview_url="http://t5"),
    ]
    _patch_picker(monkeypatch, tracks)
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    p3 = await room.add_player("Carol", None)
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)

    # non-host can't adjust
    with pytest.raises(RoomError, match="only the host"):
        await room.give_card(p2.id, p2.id)

    # host gives Bob a card -> his hand grows, kept year-sorted
    before = len(room.hands[p2.id])
    broadcasts.clear() if False else None
    await room.give_card(p1.id, p2.id)
    assert len(room.hands[p2.id]) == before + 1
    years = [c.year for c in room.hands[p2.id]]
    assert years == sorted(years)
    assert room.cumulative_scores[p2.id] == before + 1

    # take it back -> floor at 1 (Bob has 2 now, can drop to 1, not below)
    await room.take_card(p1.id, p2.id)
    assert len(room.hands[p2.id]) == 1
    with pytest.raises(RoomError, match="already at 1 card"):
        await room.take_card(p1.id, p2.id)

    # abort -> back to lobby
    await room.abort_to_lobby(p1.id)
    assert room.state == "lobby"
    assert room.hands == {} and room.turn_order == []


async def test_recency_weighting_avoids_recent_picks(room: Room) -> None:
    # FakeCatalog has 3 tracks; the real picker should spread across all three
    # before repeating (anti-clustering), and remember them across picks.
    await room.add_player("Alice", None)
    ids = [
        pick[0].id
        for _ in range(3)
        if (pick := room._pick_track_no_recycle()) is not None
    ]
    assert len(set(ids)) == 3  # all distinct — recent ones were avoided
    assert room.recent_track_ids[-3:] == ids


async def test_offline_skipped_in_rotation_and_all_offline_destroys(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None, destroyed: list
) -> None:
    tracks = [
        Track(id=f"t{i}", title=f"T{i}", artist="A", year=1980 + i, preview_url=f"http://t{i}")
        for i in range(8)
    ]
    _patch_picker(monkeypatch, tracks)
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)
    await room.place_song(p1.id, 1)  # reveal; next turn would be Bob

    # Bob goes offline → the rotation skips him, turn comes back to Alice
    await room.remove_player(p2.id)
    assert p2.id in room.disconnected and room.has_player(p2.id)
    await room.start_round(p1.id)  # advance
    await asyncio.sleep(0.05)
    assert room.current_turn_player_id == p1.id  # Bob skipped

    # Alice also drops → everyone offline → room destroyed
    await room.remove_player(p1.id)
    assert destroyed == [True]


async def test_active_player_leaving_mid_listening_resolves_turn(
    room: Room, monkeypatch: pytest.MonkeyPatch, broadcasts: list[Any]
) -> None:
    # The player on the clock leaving mid-snippet must end the turn immediately
    # (as a miss) instead of stalling the table through the snippet + placing
    # timeout. They go offline but the round moves straight to the reveal.
    monkeypatch.setattr(room_module, "HITSTER_INTRO_DURATION_S", 0)
    monkeypatch.setattr(room_module, "SNIPPET_DURATION_S", 60)
    monkeypatch.setattr(room_module, "PLACING_TIMEOUT_S", 60)
    tracks = [
        Track(id=f"t{i}", title=f"T{i}", artist="A", year=1980 + i, preview_url=f"http://t{i}")
        for i in range(6)
    ]
    _patch_picker(monkeypatch, tracks)

    p1 = await room.add_player("Alice", None)
    await room.add_player("Bob", None)
    room.steal_enabled = False  # isolate the leave→resolve path from stealing
    await room.start_round(p1.id)
    await asyncio.sleep(0.01)  # let the intro fire → listening
    assert room.state == "hitster_listening"
    active = room.current_turn_player_id
    assert active is not None

    broadcasts.clear()
    await room.remove_player(active)  # the active player drops mid-snippet

    assert room.state == "hitster_reveal"
    assert room.last_placement_result is not None
    assert room.last_placement_result.correct is False
    assert active in room.disconnected  # offline...
    assert room.has_player(active)  # ...but kept in the roster
    assert any(isinstance(m, PlacementResult) for m in broadcasts)
    room._cancel_timers()


async def test_active_turn_player_predicate(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None
) -> None:
    # is_active_turn_player gates the immediate-resolve path in the manager
    tracks = [
        Track(id=f"t{i}", title=f"T{i}", artist="A", year=1980 + i, preview_url=f"http://t{i}")
        for i in range(4)
    ]
    _patch_picker(monkeypatch, tracks)
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)

    # lobby: nobody is on the clock
    assert not room.is_active_turn_player(p1.id)

    await room.start_round(p1.id)
    await asyncio.sleep(0.05)  # → placing
    active = room.current_turn_player_id
    assert active is not None
    other = p2.id if active == p1.id else p1.id
    assert room.is_active_turn_player(active)
    assert not room.is_active_turn_player(other)
    room._cancel_timers()


# ---------- steal (open race) ----------


def _steal_tracks() -> list[Track]:
    # dealt in order (shuffle is disabled by _patch_picker):
    # p1<-1980, p2<-1990, p3<-1970, mystery<-1995
    return [
        Track(id="a", title="A", artist="A", year=1980, preview_url="http://a"),
        Track(id="b", title="B", artist="A", year=1990, preview_url="http://b"),
        Track(id="c", title="C", artist="A", year=1970, preview_url="http://c"),
        Track(id="m", title="M", artist="A", year=1995, preview_url="http://m"),
    ]


async def test_steal_opens_on_miss_and_winner_takes_card(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None
) -> None:
    _patch_picker(monkeypatch, _steal_tracks())
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    p3 = await room.add_player("Carla", None)
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)
    assert room.current_turn_player_id == p1.id

    await room.place_song(p1.id, 0)  # 1995 before 1980 → wrong → steal opens
    assert room.state == "hitster_stealing"
    assert room._steal_placer_id == p1.id
    assert set(room._steal_eligible_ids()) == {p2.id, p3.id}  # not the misser

    # the misser can't steal
    with pytest.raises(RoomError, match="can't steal"):
        await room.steal_place(p1.id, 1)

    # Bob places wrong (1995 before 1990 → no) → out, race continues
    await room.steal_place(p2.id, 0)
    assert room.state == "hitster_stealing"
    assert p2.id in room._steal_attempted
    with pytest.raises(RoomError, match="already tried"):
        await room.steal_place(p2.id, 1)

    # Carla places correctly (1995 after 1970 → slot 1) → steals the card
    await room.steal_place(p3.id, 1)
    assert room.state == "hitster_reveal"
    res = room.last_placement_result
    assert res is not None
    assert res.correct is False  # the active player still missed
    assert res.steal_offered is True
    assert res.stolen_by == p3.id
    assert len(room.hands[p3.id]) == 2
    assert room.cumulative_scores[p3.id] == 2
    assert len(room.hands[p1.id]) == 1  # misser got nothing


async def test_steal_all_miss_leaves_card_unclaimed(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None
) -> None:
    _patch_picker(monkeypatch, _steal_tracks()[:2] + [_steal_tracks()[3]])
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)

    await room.place_song(p1.id, 0)  # wrong → steal opens (only Bob eligible)
    assert room.state == "hitster_stealing"
    await room.steal_place(p2.id, 0)  # 1995 before 1990 → wrong → all out

    assert room.state == "hitster_reveal"
    res = room.last_placement_result
    assert res is not None
    assert res.steal_offered is True
    assert res.stolen_by is None
    assert len(room.hands[p2.id]) == 1  # nobody gained a card


async def test_steal_times_out_with_no_winner(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None
) -> None:
    monkeypatch.setattr(room_module, "STEAL_TIMEOUT_S", 0.05)
    _patch_picker(monkeypatch, _steal_tracks()[:2] + [_steal_tracks()[3]])
    p1 = await room.add_player("Alice", None)
    await room.add_player("Bob", None)
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)

    await room.place_song(p1.id, 0)  # wrong → steal opens
    assert room.state == "hitster_stealing"
    await asyncio.sleep(0.12)  # nobody steals → timeout
    assert room.state == "hitster_reveal"
    assert room.last_placement_result is not None
    assert room.last_placement_result.stolen_by is None


async def test_steal_disabled_reveals_directly(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None
) -> None:
    _patch_picker(monkeypatch, _steal_tracks()[:2] + [_steal_tracks()[3]])
    p1 = await room.add_player("Alice", None)
    await room.add_player("Bob", None)
    room.steal_enabled = False
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)

    await room.place_song(p1.id, 0)  # wrong, but stealing off → straight reveal
    assert room.state == "hitster_reveal"
    assert room.last_placement_result is not None
    assert room.last_placement_result.steal_offered is False


async def test_set_steal_enabled_host_only(
    room: Room, broadcasts: list[Any]
) -> None:
    from app.schemas import StealEnabledChanged

    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    assert room.steal_enabled is True  # default on
    with pytest.raises(RoomError, match="only the host"):
        await room.set_steal_enabled(p2.id, False)
    broadcasts.clear()
    await room.set_steal_enabled(p1.id, False)
    assert room.steal_enabled is False
    assert any(
        isinstance(m, StealEnabledChanged) and m.enabled is False
        for m in broadcasts
    )
    assert room.snapshot_for(p1.id).steal_enabled is False


# ---------- host-tunable round settings ----------


async def test_round_setting_ranges_and_apply(room: Room) -> None:
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    snap = room.snapshot_for(p1.id)
    assert (
        snap.snippet_duration_s,
        snap.placing_seconds,
        snap.steal_seconds,
        snap.starting_cards,
    ) == (15, 30, 12, 1)  # defaults

    with pytest.raises(RoomError, match="only the host"):
        await room.set_snippet_duration(p2.id, 20)
    with pytest.raises(RoomError, match="between"):
        await room.set_snippet_duration(p1.id, 31)
    with pytest.raises(RoomError, match="between"):
        await room.set_placing_seconds(p1.id, 4)
    with pytest.raises(RoomError, match="between"):
        await room.set_steal_seconds(p1.id, 99)
    with pytest.raises(RoomError, match="between"):
        await room.set_starting_cards(p1.id, 6)

    await room.set_snippet_duration(p1.id, 20)
    await room.set_placing_seconds(p1.id, 45)
    await room.set_steal_seconds(p1.id, 8)
    await room.set_starting_cards(p1.id, 3)
    assert (room.snippet_duration_s, room.placing_seconds, room.steal_seconds) == (
        20,
        45,
        8,
    )
    snap = room.snapshot_for(p1.id)
    assert (
        snap.snippet_duration_s,
        snap.placing_seconds,
        snap.steal_seconds,
        snap.starting_cards,
    ) == (20, 45, 8, 3)


async def test_round_settings_locked_during_game(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None
) -> None:
    tracks = [
        Track(id=f"t{i}", title=f"T{i}", artist="A", year=1980 + i, preview_url=f"http://t{i}")
        for i in range(6)
    ]
    _patch_picker(monkeypatch, tracks)
    p1 = await room.add_player("Alice", None)
    await room.add_player("Bob", None)
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)
    with pytest.raises(RoomError, match="cannot change"):
        await room.set_snippet_duration(p1.id, 20)
    room._cancel_timers()


async def test_starting_cards_deals_multiple_sorted(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None
) -> None:
    years = [1990, 1980, 2000, 1975, 1985, 1995, 1960, 2010]
    tracks = [
        Track(id=f"t{i}", title=f"T{i}", artist="A", year=y, preview_url=f"http://t{i}")
        for i, y in enumerate(years)
    ]
    _patch_picker(monkeypatch, tracks)
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    await room.set_starting_cards(p1.id, 3)
    await room.start_round(p1.id)

    assert len(room.hands[p1.id]) == 3
    assert len(room.hands[p2.id]) == 3
    assert room.cumulative_scores[p1.id] == 3
    # Alice was dealt tracks[0:3] = 1990,1980,2000 → year-sorted into a timeline
    assert [c.year for c in room.hands[p1.id]] == [1980, 1990, 2000]
    room._cancel_timers()


async def test_set_song_category_corrects_own_contribution(room: Room) -> None:
    from app.catalog import EXTRA_TRACK_PREFIX
    from app.room import ContributedTrack

    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    full_id = f"{EXTRA_TRACK_PREFIX}999"
    track = Track(
        id=full_id,
        title="Some Theme",
        artist="X",
        year=2001,
        preview_url="http://t",
        category="music",  # auto-detected (wrongly) as music
    )
    room.extra_tracks[full_id] = ContributedTrack(
        track=track, added_by_id=p1.id, added_by_name="Alice"
    )

    your = await room.set_song_category(p1.id, "999", "film_tv")
    assert room.extra_tracks[full_id].track.category == "film_tv"
    assert your[0].category == "film_tv"

    with pytest.raises(RoomError, match="unknown category"):
        await room.set_song_category(p1.id, "999", "podcast")
    with pytest.raises(RoomError, match="not found in your contributions"):
        await room.set_song_category(p2.id, "999", "music")  # not Bob's song


# ---------- AI opponents (singleplayer bots) ----------


async def test_add_bot_and_host_skips_bots(room: Room) -> None:
    bot = await room.add_bot("medium")
    assert bot.is_bot is True
    assert room.bot_difficulty[bot.id] == "medium"
    assert room.host_id is None  # a bot never hosts
    p1 = await room.add_player("Alice", None)
    assert room.host_id == p1.id  # the human hosts, not the bot
    # non-host can't add bots; unknown difficulty rejected
    p2 = await room.add_player("Bob", None)
    with pytest.raises(RoomError, match="only the host"):
        await room.add_bot("easy", requester_id=p2.id)
    with pytest.raises(RoomError, match="unknown difficulty"):
        await room.add_bot("nightmare", requester_id=p1.id)


async def test_bot_slot_heuristic(
    room: Room, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.schemas import CardSnapshot

    bot = await room.add_bot("hard")
    room.current_track = Track(
        id="m", title="M", artist="A", year=1985, preview_url="http://m"
    )
    room.hands[bot.id] = [
        CardSnapshot(track_id="a", title="A", artist="A", year=1980, artwork_url=None, added_by=None),
        CardSnapshot(track_id="b", title="B", artist="A", year=1990, artwork_url=None, added_by=None),
    ]
    # correct gap for 1985 in [1980, 1990] is slot 1
    monkeypatch.setattr(room_module.random, "random", lambda: 0.1)  # hit
    assert room._bot_slot(bot.id) == 1
    # forced miss → an adjacent *wrong* slot, never the correct one
    monkeypatch.setattr(room_module.random, "random", lambda: 0.95)
    monkeypatch.setattr(room_module.random, "choice", lambda xs: xs[0])
    assert room._bot_slot(bot.id) in (0, 2)


async def test_bot_takes_its_turn(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None
) -> None:
    monkeypatch.setattr(room_module, "BOT_THINK_S", 0.02)
    monkeypatch.setattr(room_module.random, "random", lambda: 0.1)  # hard bot hits
    tracks = [
        Track(id=f"t{i}", title=f"T{i}", artist="A", year=1980 + i, preview_url=f"http://t{i}")
        for i in range(6)
    ]
    _patch_picker(monkeypatch, tracks)
    bot = await room.add_bot("hard")  # added first → turn_order[0]
    p1 = await room.add_player("Alice", None)
    await room.start_round(p1.id)  # Alice (host) starts; the bot goes first
    await asyncio.sleep(0.15)  # intro → snippet → bot places itself
    assert room.state == "hitster_reveal"
    assert room.last_placement_result is not None
    assert room.last_placement_result.placer_id == bot.id
    assert room.last_placement_result.correct is True  # it hit
    room._cancel_timers()


async def test_bot_steals_a_missed_card(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None
) -> None:
    monkeypatch.setattr(room_module.random, "uniform", lambda a, b: 0.02)
    monkeypatch.setattr(room_module.random, "random", lambda: 0.1)  # bot hits
    tracks = [
        Track(id="a", title="A", artist="A", year=1980, preview_url="http://a"),
        Track(id="b", title="B", artist="A", year=1990, preview_url="http://b"),
        Track(id="m", title="M", artist="A", year=1995, preview_url="http://m"),
    ]
    _patch_picker(monkeypatch, tracks)
    p1 = await room.add_player("Alice", None)  # turn_order[0], goes first
    bot = await room.add_bot("hard")
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)  # → Alice placing
    await room.place_song(p1.id, 0)  # 1995 before 1980 → wrong → steal opens
    assert room.state == "hitster_stealing"
    await asyncio.sleep(0.12)  # bot races in and steals (correct)
    assert room.state == "hitster_reveal"
    assert room.last_placement_result is not None
    assert room.last_placement_result.stolen_by == bot.id
    room._cancel_timers()


async def test_is_singleplayer_detection(room: Room) -> None:
    p1 = await room.add_player("Alice", None)
    assert room._is_singleplayer() is False  # lone human, no bots
    await room.add_bot("medium")
    assert room._is_singleplayer() is True  # 1 human + bot
    await room.add_player("Bob", None)
    assert room._is_singleplayer() is False  # 2 humans → multiplayer again
    del p1


async def test_game_finish_records_stats(
    room: Room, monkeypatch: pytest.MonkeyPatch, fast_timers: None
) -> None:
    recorded: list[dict] = []
    monkeypatch.setattr(
        room_module, "record_game_result", lambda **kw: recorded.append(kw)
    )
    tracks = [
        Track(id="s1", title="S1", artist="A", year=1980, preview_url="http://s1"),
        Track(id="s2", title="S2", artist="A", year=1981, preview_url="http://s2"),
        Track(id="m1", title="M1", artist="A", year=1990, preview_url="http://m1"),
    ]
    _patch_picker(monkeypatch, tracks)
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    room.steal_enabled = False
    await room.set_card_target(p1.id, 2)
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)
    await room.place_song(p1.id, 1)  # 1990 after 1980 → correct → Alice wins
    await room.start_round(p1.id)  # podium complete → finish

    assert room.state == "game_over"
    assert len(recorded) == 1
    rec = recorded[0]
    assert rec["room_code"] == "TEST"
    assert rec["singleplayer"] is False
    by_name = {p.name: p for p in rec["players"]}
    assert by_name["Alice"].place == 1
    assert by_name["Alice"].correct == 1
    assert by_name["Alice"].final_cards == 2
    assert by_name["Bob"].place is None
    del p2


async def test_room_destroyed_when_last_human_leaves(
    room: Room, destroyed: list
) -> None:
    p1 = await room.add_player("Alice", None)
    await room.add_bot("medium")
    await room.add_bot("easy")
    assert len(room.players) == 3
    await room.remove_player(p1.id)  # only bots left → tear it down
    assert destroyed == [True]
