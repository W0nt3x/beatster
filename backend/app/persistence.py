"""Checkpoint persistence for rooms — so a restart/deploy doesn't kill a game night.

Rooms still run fully in-memory (timers and sockets stay ephemeral, by
design — we deliberately never serialize running asyncio timers). This module
only handles the files: whenever a room passes a safe *checkpoint* state
(lobby, classic_reveal, game_over) the manager writes its logical state as
JSON to ``ROOMS_DIR/<CODE>.json``; on boot the manager loads whatever is
there. A crash mid-turn therefore restores the previous checkpoint — at most
the interrupted turn is lost.

Every function here never raises: a persistence hiccup must not break live
gameplay (same rule as stats.py).
"""

import json
import logging
import os
import re
import time
from typing import Any, cast

from .config import ROOMS_DIR

log = logging.getLogger(__name__)
PERSIST_VERSION = 1
# snapshots older than this are leftovers of a long-gone game night, not
# something anyone expects to resume — dropped (and deleted) on boot
MAX_SNAPSHOT_AGE_S = 12 * 3600

_CODE_RE = re.compile(r"^[A-Z0-9]{4,12}$")


def _path(code: str) -> str:
    return os.path.join(ROOMS_DIR, f"{code}.json")


def save_room_snapshot(code: str, data: dict[str, Any]) -> None:
    """Atomically write one room's checkpoint snapshot (tmp file + replace)."""
    try:
        os.makedirs(ROOMS_DIR, exist_ok=True)
        tmp = _path(code) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, _path(code))
    except OSError as e:
        log.warning("could not save room snapshot %s: %s", code, e)


def delete_room_snapshot(code: str) -> None:
    try:
        os.remove(_path(code))
    except FileNotFoundError:
        pass
    except OSError as e:
        log.warning("could not delete room snapshot %s: %s", code, e)


def load_room_snapshots() -> list[dict[str, Any]]:
    """Read all restorable snapshots; invalid/stale files are deleted on sight."""
    try:
        names = sorted(os.listdir(ROOMS_DIR))
    except FileNotFoundError:
        return []
    except OSError as e:
        log.warning("could not list room snapshots: %s", e)
        return []

    out: list[dict[str, Any]] = []
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(ROOMS_DIR, name)
        try:
            with open(path, encoding="utf-8") as f:
                raw: Any = json.load(f)
            if not isinstance(raw, dict):
                raise ValueError("not an object")
            data = cast(dict[str, Any], raw)
            if data.get("version") != PERSIST_VERSION:
                raise ValueError(f"version {data.get('version')!r}")
            code = data.get("code")
            if not isinstance(code, str) or not _CODE_RE.match(code):
                raise ValueError(f"bad code {code!r}")
            if name != f"{code}.json":
                raise ValueError(f"filename does not match code {code!r}")
            if time.time() - float(data.get("saved_at", 0)) > MAX_SNAPSHOT_AGE_S:
                raise ValueError("stale snapshot")
            out.append(data)
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as e:
            log.warning("dropping room snapshot %s: %s", name, e)
            try:
                os.remove(path)
            except OSError:
                pass
    return out
