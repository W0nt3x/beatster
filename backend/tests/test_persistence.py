import asyncio
import json
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import persistence
from app import room as room_module
from app import room_manager as rm_module
from app.catalog import Track
from app.room_manager import RoomManager


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


@pytest.fixture(autouse=True)
def _rooms_dir(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> str:
    d = str(tmp_path / "rooms")
    monkeypatch.setattr(persistence, "ROOMS_DIR", d)
    return d


@pytest.fixture(autouse=True)
def _no_stats_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(room_module, "record_game_result", lambda **_kw: None)
    monkeypatch.setattr(room_module, "record_placement", lambda **_kw: None)
    monkeypatch.setattr(room_module, "record_activity", lambda *_a, **_kw: None)


@pytest.fixture
def fast_timers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(room_module, "SNIPPET_DURATION_S", 0)
    monkeypatch.setattr(room_module, "PLACING_TIMEOUT_S", 60)
    monkeypatch.setattr(room_module, "HITSTER_INTRO_DURATION_S", 0)


def _tracks(n: int, start_year: int = 1980) -> list[Track]:
    return [
        Track(
            id=f"t{i}",
            title=f"T{i}",
            artist="A",
            year=start_year + i,
            preview_url=f"http://t{i}",
        )
        for i in range(n)
    ]


class _TrackQueue:
    def __init__(self, tracks: list[Track]) -> None:
        self.tracks = list(tracks)
        self.idx = 0

    def pop(self) -> tuple[Track, None, None] | None:
        if self.idx >= len(self.tracks):
            return None
        t = self.tracks[self.idx]
        self.idx += 1
        return (t, None, None)


def _patch_picker(monkeypatch: pytest.MonkeyPatch, tracks: list[Track]) -> None:
    queue = _TrackQueue(tracks)
    monkeypatch.setattr(
        room_module.Room, "_pick_track_no_recycle", lambda self: queue.pop()
    )
    monkeypatch.setattr(room_module.random, "shuffle", lambda lst: None)
    monkeypatch.setattr(
        room_module.Room, "_eligible_pool_size", lambda self: len(tracks)
    )


@pytest.fixture
def catalog() -> FakeCatalog:
    return FakeCatalog(_tracks(3))


@pytest.fixture
def manager(catalog: FakeCatalog) -> RoomManager:
    return RoomManager(catalog)  # type: ignore[arg-type]


def _snapshot_path(rooms_dir: str, code: str) -> str:
    return os.path.join(rooms_dir, f"{code}.json")


def _make_fake_ws() -> MagicMock:
    ws = MagicMock()
    ws.send_json = AsyncMock()
    return ws


# ---------- lobby checkpoint ----------


async def test_lobby_checkpoint_saved_and_restored(
    manager: RoomManager, catalog: FakeCatalog, _rooms_dir: str
) -> None:
    room = manager.create_room()
    p1 = await room.add_player("Alice", None)
    await room.add_player("Bob", None)
    await room.set_card_target(p1.id, 15)
    path = _snapshot_path(_rooms_dir, room.code)
    assert os.path.exists(path)

    m2 = RoomManager(catalog)  # type: ignore[arg-type]
    assert m2.restore_rooms() == 1
    restored = m2.get(room.code)
    assert restored is not None
    assert restored.state == "lobby"
    assert restored.card_target == 15
    # humans re-add themselves on rejoin — a restored lobby roster is empty
    assert restored.players == []
    back = await restored.add_player("Alice", p1.id)
    assert back.id == p1.id
    for t in m2._restore_ttls.values():
        t.cancel()


async def test_lobby_restore_keeps_bots_and_extra_tracks(
    manager: RoomManager, catalog: FakeCatalog
) -> None:
    room = manager.create_room()
    p1 = await room.add_player("Alice", None)
    await room.add_bot(difficulty="hard", requester_id=p1.id)
    extra = Track(
        id="itunes_123",
        title="X",
        artist="Y",
        year=1999,
        preview_url="http://x",
    )
    room.extra_tracks[extra.id] = room_module.ContributedTrack(
        track=extra, added_by_id=p1.id, added_by_name="Alice"
    )
    await room.set_card_target(p1.id, 12)  # any broadcast persists the lobby

    m2 = RoomManager(catalog)  # type: ignore[arg-type]
    assert m2.restore_rooms() == 1
    restored = m2.get(room.code)
    assert restored is not None
    assert [p.is_bot for p in restored.players] == [True]
    assert restored.bot_difficulty == room.bot_difficulty
    contrib = restored.extra_tracks[extra.id]
    assert contrib.track == extra
    assert contrib.added_by_id == p1.id
    for t in m2._restore_ttls.values():
        t.cancel()


# ---------- reveal checkpoint ----------


async def _play_to_reveal(
    manager: RoomManager, monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, str, str]:
    """Two players, one correct placement -> room sits in hitster_reveal."""
    _patch_picker(monkeypatch, _tracks(8))
    room = manager.create_room()
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)  # intro (0s) + snippet (0s) -> placing
    assert room.state == "hitster_placing"
    active = room.current_turn_player_id
    assert active is not None
    # all mystery years exceed the single starting card's year -> slot 1 fits
    await room.place_song(active, 1)
    assert room.state == "hitster_reveal"
    return room, p1.id, p2.id


async def test_reveal_checkpoint_roundtrip_and_resume(
    manager: RoomManager,
    catalog: FakeCatalog,
    fast_timers: None,
    monkeypatch: pytest.MonkeyPatch,
    _rooms_dir: str,
) -> None:
    room, p1_id, p2_id = await _play_to_reveal(manager, monkeypatch)
    with open(_snapshot_path(_rooms_dir, room.code), encoding="utf-8") as f:
        assert json.load(f)["state"] == "hitster_reveal"

    m2 = RoomManager(catalog)  # type: ignore[arg-type]
    assert m2.restore_rooms() == 1
    restored = m2.get(room.code)
    assert restored is not None
    assert restored.state == "hitster_reveal"
    assert restored.hands == room.hands
    assert restored.turn_order == room.turn_order
    assert restored.played_track_ids == room.played_track_ids
    assert restored.last_placement_result == room.last_placement_result
    # everyone starts offline and resumes via the normal reconnect path
    assert restored.disconnected == {p1_id, p2_id}

    await restored.add_player("Alice", p1_id)
    assert restored.disconnected == {p2_id}
    assert restored.host_id == p1_id
    # the game continues: next turn starts (offline Bob would be skipped)
    await restored.start_round(p1_id)
    assert restored.state == "hitster_listening"
    restored._cancel_timers()
    room._cancel_timers()
    for t in m2._restore_ttls.values():
        t.cancel()


async def test_mid_turn_states_keep_previous_checkpoint(
    manager: RoomManager,
    catalog: FakeCatalog,
    fast_timers: None,
    monkeypatch: pytest.MonkeyPatch,
    _rooms_dir: str,
) -> None:
    """A crash before the first reveal restores a clean lobby."""
    _patch_picker(monkeypatch, _tracks(8))
    room = manager.create_room()
    p1 = await room.add_player("Alice", None)
    await room.add_player("Bob", None)
    await room.start_round(p1.id)
    await asyncio.sleep(0.05)
    assert room.state == "hitster_placing"  # mid-turn, nothing new persisted
    with open(_snapshot_path(_rooms_dir, room.code), encoding="utf-8") as f:
        assert json.load(f)["state"] == "lobby"

    m2 = RoomManager(catalog)  # type: ignore[arg-type]
    assert m2.restore_rooms() == 1
    restored = m2.get(room.code)
    assert restored is not None
    assert restored.state == "lobby"
    assert restored.hands == {}
    assert restored.turn_order == []
    assert restored.played_track_ids == set()
    room._cancel_timers()
    for t in m2._restore_ttls.values():
        t.cancel()


# ---------- lifecycle of snapshot files ----------


async def test_destroying_room_deletes_snapshot(
    manager: RoomManager, _rooms_dir: str
) -> None:
    room = manager.create_room()
    p1 = await room.add_player("Alice", None)
    path = _snapshot_path(_rooms_dir, room.code)
    assert os.path.exists(path)
    await room.remove_player(p1.id)  # lobby leave -> room empty -> destroyed
    assert manager.get(room.code) is None
    assert not os.path.exists(path)


async def test_stale_snapshot_dropped(
    manager: RoomManager, catalog: FakeCatalog, _rooms_dir: str
) -> None:
    room = manager.create_room()
    await room.add_player("Alice", None)
    path = _snapshot_path(_rooms_dir, room.code)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["saved_at"] = 1  # 1970 — long past MAX_SNAPSHOT_AGE_S
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    m2 = RoomManager(catalog)  # type: ignore[arg-type]
    assert m2.restore_rooms() == 0
    assert not os.path.exists(path)


async def test_corrupt_snapshot_dropped(
    catalog: FakeCatalog, _rooms_dir: str
) -> None:
    os.makedirs(_rooms_dir, exist_ok=True)
    path = os.path.join(_rooms_dir, "BROKEN.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not json")

    m2 = RoomManager(catalog)  # type: ignore[arg-type]
    assert m2.restore_rooms() == 0
    assert not os.path.exists(path)


async def test_restored_room_dropped_when_nobody_rejoins(
    manager: RoomManager,
    catalog: FakeCatalog,
    monkeypatch: pytest.MonkeyPatch,
    _rooms_dir: str,
) -> None:
    room = manager.create_room()
    await room.add_player("Alice", None)
    path = _snapshot_path(_rooms_dir, room.code)

    monkeypatch.setattr(rm_module, "RESTORED_ROOM_TTL_S", 0.05)
    m2 = RoomManager(catalog)  # type: ignore[arg-type]
    assert m2.restore_rooms() == 1
    await asyncio.sleep(0.15)
    assert m2.get(room.code) is None
    assert not os.path.exists(path)


async def test_attach_cancels_restore_ttl(
    manager: RoomManager,
    catalog: FakeCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    room = manager.create_room()
    p1 = await room.add_player("Alice", None)

    monkeypatch.setattr(rm_module, "RESTORED_ROOM_TTL_S", 0.05)
    m2 = RoomManager(catalog)  # type: ignore[arg-type]
    assert m2.restore_rooms() == 1
    m2.attach(room.code, p1.id, _make_fake_ws())
    await asyncio.sleep(0.15)
    assert m2.get(room.code) is not None
