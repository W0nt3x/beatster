"""Persistent game results, per-placement events & owner activity log — SQLite.

Three kinds of data, one zero-ops DB file:

- **Finished games** (`games` + `game_players`): one row per game/participant,
  written once at game over. The leaderboard aggregates by normalized player
  NAME (the friend-group identity — works across devices), counts wins from
  multiplayer games only (>= 2 humans; solo-vs-bots games are recorded but
  flagged so nobody farms wins off easy bots), and always excludes bots.
- **Placements** (2026-07-23): every single placement attempt (turn or steal),
  written *as it happens* — with track, year, correctness and how many years
  off a miss was. Survives aborted games; feeds the fun aggregates (hit rate
  per decade, hardest songs) and, later, richer player profiles.
- **Activity** (2026-07-23): an owner-facing event feed (rooms created, games
  started/finished/aborted, joins, song adds, searches incl. result counts —
  zero-result searches are seed-list candidates). Served by the token-guarded
  `GET /api/owner/summary` (env `BEATSTER_OWNER_TOKEN`, see main.py).

All record_* functions never raise — a stats hiccup must not break gameplay.
The DB file lives next to the catalog cache (`beatster.db`); back it up by
copying the file. Env override: BEATSTER_DB (see app/config.py).
"""

import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass

from .config import DB_PATH

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY,
    finished_at INTEGER NOT NULL,       -- unix seconds
    room_code TEXT NOT NULL,
    card_target INTEGER NOT NULL,       -- 0 for bingo (no card target there)
    singleplayer INTEGER NOT NULL,      -- 1 = one human vs bots
    human_count INTEGER NOT NULL,
    mode TEXT NOT NULL DEFAULT 'classic'  -- 'classic' | 'bingo'
);
CREATE TABLE IF NOT EXISTS game_players (
    game_id INTEGER NOT NULL REFERENCES games(id),
    name TEXT NOT NULL,                 -- display name as seen in the room
    norm_name TEXT NOT NULL,            -- lowercased/trimmed identity key
    is_bot INTEGER NOT NULL,
    place INTEGER,                      -- podium place (1..3) or NULL
    final_cards INTEGER NOT NULL,
    correct INTEGER NOT NULL,
    wrong INTEGER NOT NULL,
    steals_won INTEGER NOT NULL,
    steal_attempts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gp_game ON game_players(game_id);
CREATE INDEX IF NOT EXISTS idx_gp_norm ON game_players(norm_name);
CREATE TABLE IF NOT EXISTS placements (
    id INTEGER PRIMARY KEY,
    ts INTEGER NOT NULL,                -- unix seconds
    room_code TEXT NOT NULL,
    kind TEXT NOT NULL,                 -- 'turn' | 'steal'
    name TEXT NOT NULL,
    norm_name TEXT NOT NULL,
    is_bot INTEGER NOT NULL,
    singleplayer INTEGER NOT NULL,      -- solo-vs-bots context, like games
    track_id TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    year INTEGER NOT NULL,
    correct INTEGER NOT NULL,
    timed_out INTEGER NOT NULL,         -- turn ran out with no placement
    off_by INTEGER                      -- years off the chosen gap; 0 = hit, NULL = timeout
);
CREATE INDEX IF NOT EXISTS idx_pl_norm ON placements(norm_name);
CREATE INDEX IF NOT EXISTS idx_pl_track ON placements(track_id);
CREATE INDEX IF NOT EXISTS idx_pl_ts ON placements(ts);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY,
    ts INTEGER NOT NULL,
    type TEXT NOT NULL,
    room_code TEXT,
    detail TEXT                          -- compact JSON payload
);
CREATE INDEX IF NOT EXISTS idx_act_ts ON activity(ts);
CREATE INDEX IF NOT EXISTS idx_act_type ON activity(type);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        # 2026-07-24 (bingo mode): games gained a mode column; ALTER is the
        # whole migration story for this DB — existing rows default to classic
        try:
            conn.execute(
                "ALTER TABLE games ADD COLUMN mode TEXT NOT NULL"
                " DEFAULT 'classic'"
            )
        except sqlite3.OperationalError:
            pass  # column already exists
    log.info("stats db ready: %s", DB_PATH)


def norm_name(name: str) -> str:
    return name.strip().lower()


@dataclass(frozen=True, slots=True)
class PlayerResult:
    name: str
    is_bot: bool
    place: int | None
    final_cards: int
    correct: int
    wrong: int
    steals_won: int
    steal_attempts: int


def record_game_result(
    room_code: str,
    card_target: int,
    singleplayer: bool,
    players: list[PlayerResult],
    mode: str = "classic",
) -> None:
    """Persist one finished game. Never raises — losing one stats row must not
    break the game-over flow."""
    try:
        human_count = sum(1 for p in players if not p.is_bot)
        with _connect() as conn:
            cur = conn.execute(
                "INSERT INTO games (finished_at, room_code, card_target,"
                " singleplayer, human_count, mode) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    int(time.time()),
                    room_code,
                    card_target,
                    1 if singleplayer else 0,
                    human_count,
                    mode,
                ),
            )
            game_id = cur.lastrowid
            conn.executemany(
                "INSERT INTO game_players (game_id, name, norm_name, is_bot,"
                " place, final_cards, correct, wrong, steals_won,"
                " steal_attempts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        game_id,
                        p.name,
                        norm_name(p.name),
                        1 if p.is_bot else 0,
                        p.place,
                        p.final_cards,
                        p.correct,
                        p.wrong,
                        p.steals_won,
                        p.steal_attempts,
                    )
                    for p in players
                ],
            )
        log.info(
            "recorded game %s: %d players (%d human, sp=%s)",
            room_code,
            len(players),
            human_count,
            singleplayer,
        )
    except Exception as e:  # noqa: BLE001 — stats must never kill a game
        log.warning("could not record game result: %s", e)


def leaderboard(limit: int = 20) -> list[dict[str, object]]:
    """Career stats per human player from MULTIPLAYER games (>= 2 humans),
    ranked by wins, then win rate, then correct placements."""
    query = """
        SELECT
            gp.norm_name,
            -- latest display spelling of the name
            (SELECT gp2.name FROM game_players gp2
              WHERE gp2.norm_name = gp.norm_name AND gp2.is_bot = 0
              ORDER BY gp2.game_id DESC LIMIT 1) AS display_name,
            COUNT(*) AS games,
            SUM(CASE WHEN gp.place = 1 THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN gp.place IS NOT NULL THEN 1 ELSE 0 END) AS podiums,
            SUM(gp.correct) AS correct,
            SUM(gp.wrong) AS wrong,
            SUM(gp.steals_won) AS steals_won
        FROM game_players gp
        JOIN games g ON g.id = gp.game_id
        WHERE gp.is_bot = 0 AND g.singleplayer = 0 AND g.human_count >= 2
        GROUP BY gp.norm_name
        ORDER BY wins DESC, CAST(wins AS REAL) / COUNT(*) DESC, correct DESC
        LIMIT ?
    """
    with _connect() as conn:
        rows = conn.execute(query, (limit,)).fetchall()
    return [
        {
            "name": r[1] or r[0],
            "games": r[2],
            "wins": r[3],
            "podiums": r[4],
            "correct": r[5],
            "wrong": r[6],
            "steals_won": r[7],
        }
        for r in rows
    ]


def totals() -> dict[str, int]:
    with _connect() as conn:
        games = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(singleplayer = 0), 0) FROM games"
        ).fetchone()
    return {"games_recorded": games[0], "multiplayer_games": games[1]}


# ---------- per-placement events + owner activity log ----------


def record_placement(
    *,
    room_code: str,
    kind: str,
    name: str,
    is_bot: bool,
    singleplayer: bool,
    track_id: str,
    title: str,
    artist: str,
    year: int,
    correct: bool,
    timed_out: bool,
    off_by: int | None,
) -> None:
    """Persist one placement attempt (turn or steal). Never raises."""
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO placements (ts, room_code, kind, name, norm_name,"
                " is_bot, singleplayer, track_id, title, artist, year,"
                " correct, timed_out, off_by)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    int(time.time()),
                    room_code,
                    kind,
                    name,
                    norm_name(name),
                    1 if is_bot else 0,
                    1 if singleplayer else 0,
                    track_id,
                    title,
                    artist,
                    year,
                    1 if correct else 0,
                    1 if timed_out else 0,
                    off_by,
                ),
            )
    except Exception as e:  # noqa: BLE001 — stats must never kill a game
        log.warning("could not record placement: %s", e)


def record_activity(
    kind: str,
    room_code: str | None = None,
    detail: dict[str, object] | None = None,
) -> None:
    """Append one event to the owner activity feed. Never raises."""
    try:
        payload = (
            json.dumps(detail, ensure_ascii=False, separators=(",", ":"))
            if detail
            else None
        )
        with _connect() as conn:
            conn.execute(
                "INSERT INTO activity (ts, type, room_code, detail)"
                " VALUES (?, ?, ?, ?)",
                (int(time.time()), kind, room_code, payload),
            )
    except Exception as e:  # noqa: BLE001
        log.warning("could not record activity: %s", e)


def owner_summary(days: int = 14) -> dict[str, object]:
    """Everything the site owner wants at a glance (token-guarded endpoint)."""
    since = int(time.time()) - days * 86400
    with _connect() as conn:
        act_rows = conn.execute(
            "SELECT date(ts,'unixepoch') AS day, type, COUNT(*)"
            " FROM activity WHERE ts >= ? GROUP BY day, type",
            (since,),
        ).fetchall()
        pl_rows = conn.execute(
            "SELECT date(ts,'unixepoch') AS day, COUNT(*),"
            " COALESCE(SUM(correct), 0)"
            " FROM placements WHERE ts >= ? GROUP BY day",
            (since,),
        ).fetchall()
        recent = conn.execute(
            "SELECT ts, type, room_code, detail FROM activity"
            " ORDER BY id DESC LIMIT 50"
        ).fetchall()
        zero_searches = conn.execute(
            "SELECT json_extract(detail,'$.q') AS q, COUNT(*), MAX(ts)"
            " FROM activity"
            " WHERE type = 'search' AND json_extract(detail,'$.results') = 0"
            " GROUP BY q ORDER BY MAX(ts) DESC LIMIT 30"
        ).fetchall()
        hardest = conn.execute(
            "SELECT title, artist, year, COUNT(*), COALESCE(SUM(correct), 0)"
            " FROM placements WHERE is_bot = 0 AND kind = 'turn'"
            " GROUP BY track_id HAVING COUNT(*) >= 3"
            " ORDER BY 1.0 * SUM(correct) / COUNT(*) ASC, COUNT(*) DESC"
            " LIMIT 15"
        ).fetchall()
        decades = conn.execute(
            "SELECT (year / 10) * 10 AS decade, COUNT(*),"
            " COALESCE(SUM(correct), 0)"
            " FROM placements WHERE is_bot = 0 AND kind = 'turn'"
            " GROUP BY decade ORDER BY decade"
        ).fetchall()
        counts = conn.execute(
            "SELECT (SELECT COUNT(*) FROM placements),"
            " (SELECT COUNT(*) FROM activity)"
        ).fetchone()

    per_day: dict[str, dict[str, int]] = {}
    for day, kind, n in act_rows:
        per_day.setdefault(day, {})[kind] = n
    for day, n, hits in pl_rows:
        bucket = per_day.setdefault(day, {})
        bucket["placements"] = n
        bucket["placements_correct"] = hits

    return {
        "totals": {
            **totals(),
            "placements": counts[0],
            "activity_events": counts[1],
        },
        "per_day": [
            {"day": day, **kinds} for day, kinds in sorted(per_day.items())
        ],
        "recent_activity": [
            {
                "ts": r[0],
                "type": r[1],
                "room": r[2],
                "detail": json.loads(r[3]) if r[3] else None,
            }
            for r in recent
        ],
        "zero_result_searches": [
            {"q": r[0], "times": r[1], "last_ts": r[2]} for r in zero_searches
        ],
        "hardest_tracks": [
            {
                "title": r[0],
                "artist": r[1],
                "year": r[2],
                "attempts": r[3],
                "hits": r[4],
            }
            for r in hardest
        ],
        "decade_hit_rate": [
            {"decade": r[0], "attempts": r[1], "hits": r[2]} for r in decades
        ],
    }
