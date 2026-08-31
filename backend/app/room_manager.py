import asyncio
import logging
import random
from dataclasses import dataclass

from fastapi import WebSocket

from . import persistence
from .catalog import Catalog
from .room import CHECKPOINT_STATES, BroadcastMessage, Broadcaster, OnEmpty, Room

log = logging.getLogger(__name__)

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/I/1/L
CODE_LENGTH = 6
RECONNECT_GRACE_S = 5
# the player on the clock holds up the whole table, so they get a much shorter
# grace before their turn is resolved — long enough to ride out a quick reload
# or network blip, short enough that a real leave doesn't stall everyone
ACTIVE_TURN_GRACE_S = 3
# rooms restored from a checkpoint snapshot have no connections; if nobody
# rejoins within this window the room (and its snapshot file) is dropped
RESTORED_ROOM_TTL_S = 10 * 60


def _generate_code() -> str:
    return "".join(random.choices(CODE_ALPHABET, k=CODE_LENGTH))


@dataclass
class _Connection:
    player_id: str
    ws: WebSocket


class RoomManager:
    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog
        self._rooms: dict[str, Room] = {}
        self._conns: dict[str, list[_Connection]] = {}
        self._pending_removals: dict[tuple[str, str], asyncio.Task[None]] = {}
        # per restored room: the drop-if-nobody-rejoins timer (see restore_rooms)
        self._restore_ttls: dict[str, asyncio.Task[None]] = {}

    def _room_callbacks(self, code: str) -> tuple[Broadcaster, OnEmpty]:
        async def broadcast(msg: BroadcastMessage) -> None:
            await self._broadcast(code, msg)

        async def on_empty() -> None:
            await self._destroy(code)

        return broadcast, on_empty

    def create_room(self) -> Room:
        code: str | None = None
        for _ in range(10):
            candidate = _generate_code()
            if candidate not in self._rooms:
                code = candidate
                break
        if code is None:
            raise RuntimeError("could not allocate room code (too many collisions)")

        broadcast, on_empty = self._room_callbacks(code)
        room = Room(
            code=code,
            catalog=self._catalog,
            broadcast=broadcast,
            on_empty=on_empty,
        )
        self._rooms[code] = room
        self._conns[code] = []
        log.info("room created: %s", code)
        return room

    def restore_rooms(self) -> int:
        """Recreate rooms from checkpoint snapshots (called once at startup).

        Restored rooms are timerless and everyone is offline; players resume
        via the normal reconnect path. Each restored room gets a TTL — if
        nobody rejoins, it is destroyed and its snapshot deleted.
        """
        restored = 0
        for data in persistence.load_room_snapshots():
            code = str(data.get("code", ""))
            if not code or code in self._rooms:
                continue
            broadcast, on_empty = self._room_callbacks(code)
            try:
                room = Room.from_persist(
                    data, self._catalog, broadcast, on_empty
                )
            except Exception as e:  # noqa: BLE001 — one bad snapshot must not block boot
                log.warning("could not restore room %s: %s", code, e)
                persistence.delete_room_snapshot(code)
                continue
            self._rooms[code] = room
            self._conns[code] = []
            self._restore_ttls[code] = asyncio.create_task(
                self._drop_if_never_rejoined(code)
            )
            restored += 1
            log.info(
                "restored room %s (state=%s, %d players)",
                code,
                room.state,
                len(room.players),
            )
        return restored

    async def _drop_if_never_rejoined(self, code: str) -> None:
        try:
            await asyncio.sleep(RESTORED_ROOM_TTL_S)
        except asyncio.CancelledError:
            return
        self._restore_ttls.pop(code, None)
        if self._conns.get(code):
            return  # someone is here — normal lifecycle owns the room now
        if code in self._rooms:
            log.info("restored room %s never rejoined — dropping", code)
            await self._destroy(code)

    def get(self, code: str) -> Room | None:
        return self._rooms.get(code)

    def attach(self, code: str, player_id: str, ws: WebSocket) -> None:
        # cancel any pending removal — the player is back before grace expired
        key = (code, player_id)
        pending = self._pending_removals.pop(key, None)
        if pending is not None and not pending.done():
            pending.cancel()
            log.info("reconnect grace canceled for %s in %s", player_id, code)
        # first connection into a restored room — its TTL no longer applies
        ttl = self._restore_ttls.pop(code, None)
        if ttl is not None and not ttl.done():
            ttl.cancel()
        self._conns.setdefault(code, []).append(_Connection(player_id, ws))

    def detach(self, code: str, player_id: str, ws: WebSocket) -> bool:
        """Remove the given connection. Returns True if this was the player's last."""
        conns = self._conns.get(code, [])
        self._conns[code] = [
            c for c in conns if not (c.player_id == player_id and c.ws is ws)
        ]
        return not any(c.player_id == player_id for c in self._conns[code])

    def handle_disconnect(self, code: str, player_id: str) -> None:
        """A player's last socket dropped.

        If they're the one currently on the clock, give them only a short grace
        (ACTIVE_TURN_GRACE_S) before resolving their turn — the table is waiting
        on them, but a quick reload / network blip mid-turn shouldn't instantly
        forfeit it. Everyone else gets the full reconnect grace. Reconnecting
        within the grace cancels removal and restores cards + score either way.
        """
        room = self._rooms.get(code)
        if room is not None and room.is_active_turn_player(player_id):
            self.schedule_removal(code, player_id, delay=ACTIVE_TURN_GRACE_S)
        else:
            self.schedule_removal(code, player_id)

    def schedule_removal(
        self, code: str, player_id: str, delay: float | None = None
    ) -> None:
        """Defer remove_player by `delay`s; cancel-on-reconnect via attach()."""
        # resolve the default at call time (not definition time) so tests can
        # monkeypatch RECONNECT_GRACE_S
        if delay is None:
            delay = RECONNECT_GRACE_S
        key = (code, player_id)
        existing = self._pending_removals.get(key)
        if existing is not None and not existing.done():
            existing.cancel()

        async def remove_after_grace() -> None:
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return
            self._pending_removals.pop(key, None)
            room = self._rooms.get(code)
            if room is None:
                return
            if any(c.player_id == player_id for c in self._conns.get(code, [])):
                # they reconnected via a separate code path between cancel and now
                return
            await room.remove_player(player_id)

        self._pending_removals[key] = asyncio.create_task(remove_after_grace())

    async def _broadcast(self, code: str, msg: BroadcastMessage) -> None:
        payload = msg.model_dump()
        for c in list(self._conns.get(code, [])):
            try:
                await c.ws.send_json(payload)
            except Exception as e:
                log.warning("broadcast send failed for %s: %s", code, e)
        # every mutation broadcasts, so this is the one natural persistence
        # hook: snapshot the room whenever it is in a checkpoint state (mid-
        # turn states are skipped — the file keeps the previous checkpoint,
        # which is exactly where a restore should resume)
        room = self._rooms.get(code)
        if room is not None and room.state in CHECKPOINT_STATES:
            persistence.save_room_snapshot(code, room.to_persist())

    async def _destroy(self, code: str) -> None:
        log.info("room destroyed: %s", code)
        self._rooms.pop(code, None)
        self._conns.pop(code, None)
        ttl = self._restore_ttls.pop(code, None)
        if ttl is not None and not ttl.done():
            ttl.cancel()
        persistence.delete_room_snapshot(code)
        # cancel any still-pending removals for this room
        for key in list(self._pending_removals.keys()):
            if key[0] == code:
                task = self._pending_removals.pop(key)
                if not task.done():
                    task.cancel()
