import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import persistence
from app import room_manager as rm_module
from app.catalog import Track
from app.room_manager import RoomManager


@pytest.fixture(autouse=True)
def _rooms_dir(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # manager broadcasts persist checkpoint snapshots — keep them off the real dir
    monkeypatch.setattr(persistence, "ROOMS_DIR", str(tmp_path / "rooms"))


class FakeCatalog:
    tracks = [
        Track(id="t", title="T", artist="A", year=2000, preview_url="http://t")
    ]

    def available_categories(self) -> list[str]:
        return ["music"]

    def category_counts(self) -> dict[str, int]:
        return {"music": 1}


@pytest.fixture
def fast_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rm_module, "RECONNECT_GRACE_S", 0.05)


@pytest.fixture
def manager() -> RoomManager:
    return RoomManager(FakeCatalog())  # type: ignore[arg-type]


def _make_fake_ws() -> MagicMock:
    ws = MagicMock()
    ws.send_json = AsyncMock()
    return ws


async def test_grace_period_removes_player_after_timeout(
    manager: RoomManager, fast_grace: None
) -> None:
    room = manager.create_room()
    ws = _make_fake_ws()
    p = await room.add_player("Alice", None)
    manager.attach(room.code, p.id, ws)

    last = manager.detach(room.code, p.id, ws)
    assert last is True
    manager.schedule_removal(room.code, p.id)

    # before grace expires
    await asyncio.sleep(0.02)
    assert room.has_player(p.id)

    # after grace expires
    await asyncio.sleep(0.1)
    assert not room.has_player(p.id)


async def test_reconnect_within_grace_cancels_removal(
    manager: RoomManager, fast_grace: None
) -> None:
    room = manager.create_room()
    ws1 = _make_fake_ws()
    p = await room.add_player("Alice", None)
    manager.attach(room.code, p.id, ws1)

    last = manager.detach(room.code, p.id, ws1)
    assert last is True
    manager.schedule_removal(room.code, p.id)

    # reconnect almost immediately
    await asyncio.sleep(0.02)
    ws2 = _make_fake_ws()
    manager.attach(room.code, p.id, ws2)

    # well past original grace
    await asyncio.sleep(0.1)
    assert room.has_player(p.id)


async def test_active_turn_player_uses_short_grace(
    manager: RoomManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the player on the clock is resolved on the short active-turn grace; the
    # full reconnect grace would leave them around far longer
    monkeypatch.setattr(rm_module, "ACTIVE_TURN_GRACE_S", 0.05)
    monkeypatch.setattr(rm_module, "RECONNECT_GRACE_S", 5)
    room = manager.create_room()
    ws = _make_fake_ws()
    p = await room.add_player("Alice", None)
    manager.attach(room.code, p.id, ws)
    # pretend it's this player's turn so handle_disconnect takes the fast path
    monkeypatch.setattr(room, "is_active_turn_player", lambda _pid: True)

    assert manager.detach(room.code, p.id, ws) is True
    manager.handle_disconnect(room.code, p.id)

    # past the short grace but well under the full reconnect grace
    await asyncio.sleep(0.12)
    assert not room.has_player(p.id)


async def test_non_active_player_uses_full_grace(
    manager: RoomManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a player who isn't on the clock keeps the full reconnect grace
    monkeypatch.setattr(rm_module, "ACTIVE_TURN_GRACE_S", 0.05)
    monkeypatch.setattr(rm_module, "RECONNECT_GRACE_S", 5)
    room = manager.create_room()
    ws = _make_fake_ws()
    p = await room.add_player("Alice", None)
    manager.attach(room.code, p.id, ws)

    assert manager.detach(room.code, p.id, ws) is True
    manager.handle_disconnect(room.code, p.id)

    # past the short grace — but not the full one, so they're still here
    await asyncio.sleep(0.12)
    assert room.has_player(p.id)


async def test_multiple_tabs_only_schedule_on_last_close(
    manager: RoomManager, fast_grace: None
) -> None:
    room = manager.create_room()
    ws1 = _make_fake_ws()
    ws2 = _make_fake_ws()
    p = await room.add_player("Alice", None)
    manager.attach(room.code, p.id, ws1)
    manager.attach(room.code, p.id, ws2)

    last_first = manager.detach(room.code, p.id, ws1)
    assert last_first is False  # ws2 still open

    # past grace — but no removal was scheduled, so player stays
    await asyncio.sleep(0.1)
    assert room.has_player(p.id)

    last_second = manager.detach(room.code, p.id, ws2)
    assert last_second is True
    manager.schedule_removal(room.code, p.id)
    await asyncio.sleep(0.1)
    assert not room.has_player(p.id)
