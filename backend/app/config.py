"""Central runtime configuration — every path and env knob in one place.

Design: ONE base directory (``BEATSTER_DATA_DIR``) holds all mutable state
(catalog cache, community songs, stats DB, room snapshots), so a fresh or
self-hosted instance needs at most one env var — or none at all (default
``~/.cache/beatster``). Every path can still be overridden individually
(that's how a production service unit pins its paths to a system location),
and the individual override wins.

Every knob is read from ``BEATSTER_<NAME>``.

Consumers import these as module globals (``from .config import ...``) into
their own namespace so tests can keep monkeypatching e.g. ``stats.DB_PATH``.
The owner token (``BEATSTER_OWNER_TOKEN``) is intentionally NOT read here:
main.py reads it per-request so tests can setenv/delenv it at runtime.
"""

import os


def _env(name: str) -> str | None:
    return os.environ.get(f"BEATSTER_{name}")


def _env_path(name: str, default: str) -> str:
    value = _env(name)
    return os.path.expanduser(value) if value else default


# The one knob: base directory for all mutable state.
DATA_DIR = _env_path("DATA_DIR", os.path.expanduser("~/.cache/beatster"))

# Pre-built seed-catalog cache (see tools/build_cache.py — never live-resolved
# at startup, rate limits).
CATALOG_CACHE_PATH = _env_path(
    "CATALOG_CACHE", os.path.join(DATA_DIR, "catalog.json")
)

_CACHE_DIR = os.path.dirname(CATALOG_CACHE_PATH) or "."

# Player-added songs, persisted next to the catalog cache (merged into the
# pool on load; never overwritten by a cache rebuild).
COMMUNITY_PATH = os.path.join(_CACHE_DIR, "community_tracks.json")

# SQLite stats DB (finished games, placements, owner activity feed).
DB_PATH = _env_path("DB", os.path.join(_CACHE_DIR, "beatster.db"))

# Room checkpoint snapshots (survive restarts/deploys).
ROOMS_DIR = _env_path("ROOMS_DIR", os.path.join(_CACHE_DIR, "rooms"))

# Optional: serve the built frontend (frontend/dist) straight from FastAPI —
# the single-process self-host mode (Docker image sets this). Production
# leaves it unset and lets nginx serve the static files.
STATIC_DIR = _env_path("STATIC_DIR", "")

# Contact for the MusicBrainz User-Agent in tools/check_years.py — MB's API
# etiquette requires a way to reach whoever is hammering them (1 req/s).
MB_CONTACT = _env("MB_CONTACT") or ""
