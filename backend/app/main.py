import json
import logging
import os
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import TypeAdapter, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import Scope

import asyncio

from . import config
from .catalog import catalog, itunes_search
from .room import RoomError
from .room_manager import RoomManager
from .stats import init_db, leaderboard, owner_summary, record_activity, totals
from .schemas import (
    AddBot,
    AddSong,
    BingoAnswer,
    BingoErase,
    BingoMark,
    ClientMessage,
    AbortToLobby,
    EndGame,
    GiveCard,
    Join,
    Joined,
    KickPlayer,
    PlaceSong,
    TakeCard,
    Rematch,
    RemoveSong,
    ServerError,
    SetAudioMode,
    SetBingoAnswerSeconds,
    SetBingoCategories,
    SetGameMode,
    SetSongCategory,
    SetCardTarget,
    SetCategoryFilter,
    SetOnlyPlayerAdded,
    SetPlacingSeconds,
    SetAvatar,
    SetPromo,
    SetSnippetDuration,
    SetSongsPerPlayer,
    SetStartingCards,
    SetStealEnabled,
    SetStealSeconds,
    StartRound,
    StealPlace,
    YourExtraTracksChanged,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

manager = RoomManager(catalog)
_client_msg_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    init_db()
    await catalog.load()
    # bring back rooms that were live before the last restart/deploy; a failed
    # restore must never block startup (snapshots are best-effort by design)
    try:
        restored = manager.restore_rooms()
        if restored:
            log.info("restored %d room(s) from checkpoint snapshots", restored)
    except Exception as e:  # noqa: BLE001
        log.warning("room restore failed: %s", e)
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/rooms")
async def create_room(bots: int = 0, difficulty: str = "medium") -> dict[str, str]:
    room = manager.create_room()
    # singleplayer: pre-seed AI opponents so the room is ready to play
    for _ in range(max(0, min(bots, 5))):
        try:
            await room.add_bot(difficulty=difficulty)
        except RoomError:
            break
    record_activity("room_created", room.code, {"bots": len(room.players)})
    return {"code": room.code}


@app.get("/api/search")
async def search_songs(q: str = "") -> dict[str, list[dict[str, str]]]:
    results = await itunes_search(q)
    if q.strip():
        # zero-result searches are the interesting ones: seed-list candidates
        record_activity(
            "search", None, {"q": q.strip()[:120], "results": len(results)}
        )
    return {"results": results}


@app.get("/api/stats")
async def get_stats() -> dict[str, object]:
    # tiny queries, but keep the event loop clean anyway
    board = await asyncio.to_thread(leaderboard)
    t = await asyncio.to_thread(totals)
    return {"leaderboard": board, "totals": t}


def _owner_token_ok(token: str) -> bool:
    """The owner endpoint is enabled by setting BEATSTER_OWNER_TOKEN in the
    service environment; without it (e.g. local dev) the endpoint stays off.
    Read per-request, not at import, so tests can setenv/delenv it."""
    expected = os.environ.get("BEATSTER_OWNER_TOKEN") or ""
    return bool(expected) and secrets.compare_digest(token, expected)


@app.get("/api/owner/summary")
async def get_owner_summary(token: str = "", days: int = 14) -> dict[str, object]:
    if not _owner_token_ok(token):
        raise HTTPException(status_code=403, detail="forbidden")
    return await asyncio.to_thread(owner_summary, max(1, min(days, 90)))


async def _recv_client_msg(ws: WebSocket) -> ClientMessage | None:
    try:
        raw = await ws.receive_json()
    except json.JSONDecodeError as e:
        await ws.send_json(ServerError(message=f"invalid json: {e}").model_dump())
        return None
    try:
        return _client_msg_adapter.validate_python(raw)
    except ValidationError as e:
        await ws.send_json(ServerError(message=f"invalid message: {e}").model_dump())
        return None


@app.websocket("/ws/{code}")
async def ws_room(ws: WebSocket, code: str) -> None:
    code = code.upper()
    await ws.accept()

    room = manager.get(code)
    if room is None:
        await ws.send_json(
            ServerError(message=f"room {code} not found").model_dump()
        )
        await ws.close(code=4404)
        return

    player_id: str | None = None
    try:
        first = await _recv_client_msg(ws)
        if first is None:
            await ws.close(code=4400)
            return
        if not isinstance(first, Join):
            await ws.send_json(
                ServerError(message="first message must be join").model_dump()
            )
            await ws.close(code=4400)
            return

        player = await room.add_player(
            name=first.name, player_id=first.player_id, avatar=first.avatar
        )
        player_id = player.id
        manager.attach(code, player_id, ws)
        await ws.send_json(
            Joined(
                player_id=player_id,
                room_code=code,
                snapshot=room.snapshot_for(player_id),
            ).model_dump()
        )
        log.info("ws joined: room=%s player=%s name=%s", code, player_id, player.name)

        while True:
            msg = await _recv_client_msg(ws)
            if msg is None:
                continue
            try:
                if isinstance(msg, StartRound):
                    await room.start_round(requester_id=player_id)
                elif isinstance(msg, SetCategoryFilter):
                    await room.set_category_filter(
                        requester_id=player_id, categories=msg.categories
                    )
                elif isinstance(msg, SetOnlyPlayerAdded):
                    await room.set_only_player_added(
                        requester_id=player_id, only=msg.only
                    )
                elif isinstance(msg, SetCardTarget):
                    await room.set_card_target(
                        requester_id=player_id, card_target=msg.card_target
                    )
                elif isinstance(msg, SetSongsPerPlayer):
                    await room.set_songs_per_player(
                        requester_id=player_id,
                        songs_per_player=msg.songs_per_player,
                    )
                elif isinstance(msg, SetAudioMode):
                    await room.set_audio_mode(
                        requester_id=player_id, mode=msg.mode
                    )
                elif isinstance(msg, SetSnippetDuration):
                    await room.set_snippet_duration(
                        requester_id=player_id, seconds=msg.seconds
                    )
                elif isinstance(msg, SetPlacingSeconds):
                    await room.set_placing_seconds(
                        requester_id=player_id, seconds=msg.seconds
                    )
                elif isinstance(msg, SetStealSeconds):
                    await room.set_steal_seconds(
                        requester_id=player_id, seconds=msg.seconds
                    )
                elif isinstance(msg, SetStartingCards):
                    await room.set_starting_cards(
                        requester_id=player_id, count=msg.count
                    )
                elif isinstance(msg, SetStealEnabled):
                    await room.set_steal_enabled(
                        requester_id=player_id, enabled=msg.enabled
                    )
                elif isinstance(msg, SetGameMode):
                    await room.set_game_mode(
                        requester_id=player_id, mode=msg.mode
                    )
                elif isinstance(msg, SetBingoCategories):
                    await room.set_bingo_categories(
                        requester_id=player_id, categories=msg.categories
                    )
                elif isinstance(msg, SetBingoAnswerSeconds):
                    await room.set_bingo_answer_seconds(
                        requester_id=player_id, seconds=msg.seconds
                    )
                elif isinstance(msg, BingoAnswer):
                    await room.submit_bingo_answer(
                        player_id=player_id, value=msg.value
                    )
                elif isinstance(msg, BingoMark):
                    await room.bingo_mark(player_id=player_id, cell=msg.cell)
                elif isinstance(msg, BingoErase):
                    await room.bingo_erase(
                        player_id=player_id,
                        target_id=msg.target_id,
                        cell=msg.cell,
                    )
                elif isinstance(msg, StealPlace):
                    await room.steal_place(
                        player_id=player_id, slot_index=msg.slot_index
                    )
                elif isinstance(msg, SetAvatar):
                    await room.set_avatar(
                        player_id=player_id, avatar=msg.avatar
                    )
                elif isinstance(msg, SetPromo):
                    await room.set_promo(
                        requester_id=player_id, active=msg.active
                    )
                elif isinstance(msg, PlaceSong):
                    await room.place_song(
                        player_id=player_id, slot_index=msg.slot_index
                    )
                elif isinstance(msg, AddSong):
                    your_list = await room.add_song(
                        player_id=player_id, raw_track_id=msg.track_id
                    )
                    await ws.send_json(
                        YourExtraTracksChanged(
                            your_extra_tracks=your_list
                        ).model_dump()
                    )
                elif isinstance(msg, RemoveSong):
                    your_list = await room.remove_song(
                        player_id=player_id, raw_track_id=msg.track_id
                    )
                    await ws.send_json(
                        YourExtraTracksChanged(
                            your_extra_tracks=your_list
                        ).model_dump()
                    )
                elif isinstance(msg, SetSongCategory):
                    your_list = await room.set_song_category(
                        player_id=player_id,
                        raw_track_id=msg.track_id,
                        category=msg.category,
                    )
                    await ws.send_json(
                        YourExtraTracksChanged(
                            your_extra_tracks=your_list
                        ).model_dump()
                    )
                elif isinstance(msg, AddBot):
                    await room.add_bot(
                        difficulty=msg.difficulty, requester_id=player_id
                    )
                elif isinstance(msg, KickPlayer):
                    await room.kick_player(
                        requester_id=player_id, target_id=msg.target_id
                    )
                elif isinstance(msg, GiveCard):
                    await room.give_card(
                        requester_id=player_id, target_id=msg.target_id
                    )
                elif isinstance(msg, TakeCard):
                    await room.take_card(
                        requester_id=player_id, target_id=msg.target_id
                    )
                elif isinstance(msg, AbortToLobby):
                    await room.abort_to_lobby(requester_id=player_id)
                elif isinstance(msg, EndGame):
                    await room.end_game(requester_id=player_id)
                elif isinstance(msg, Rematch):
                    await room.rematch(requester_id=player_id)
                else:  # Join after the first one
                    await ws.send_json(
                        ServerError(message="already joined").model_dump()
                    )
            except RoomError as e:
                await ws.send_json(ServerError(message=str(e)).model_dump())
    except WebSocketDisconnect:
        pass
    finally:
        if player_id is not None:
            last = manager.detach(code, player_id, ws)
            if last:
                manager.handle_disconnect(code, player_id)


class _SpaStaticFiles(StaticFiles):
    """Built frontend with SPA fallback, mirroring the production nginx
    config: unknown extension-less paths (e.g. /r/CODE) serve index.html, and
    the two update-critical files (index.html, version.json — the auto-update
    mechanism polls the latter) are never cached."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # StaticFiles RAISES (starlette's HTTPException, the PARENT of
            # fastapi's — catching the fastapi subclass would miss it) on a
            # missing file instead of returning a 404 response. Catch it for
            # the SPA fallback, but only for extension-less paths so missing
            # assets still 404.
            if exc.status_code != 404 or "." in path.rsplit("/", 1)[-1]:
                raise
            path = "index.html"
            response = await super().get_response(path, scope)
        if path in (".", "index.html", "version.json"):
            response.headers["Cache-Control"] = "no-cache"
        return response


# Single-process self-host mode: serve the built frontend straight from
# FastAPI when BEATSTER_STATIC_DIR points at a dist/ dir. Registered after all
# routes, so /api/* and /ws/* keep winning. Production (nginx serves static)
# leaves the env unset and this stays off.
if config.STATIC_DIR and os.path.isdir(config.STATIC_DIR):
    app.mount(
        "/",
        _SpaStaticFiles(directory=config.STATIC_DIR, html=True),
        name="frontend",
    )
    log.info("serving frontend from %s", config.STATIC_DIR)
