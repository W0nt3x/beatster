"""Build the catalog cache OFFLINE, gently, and write it to disk.

The catalog is large (~480 tracks). Resolving all of it live against iTunes at
server startup trips the rate limiter (HTTP 429/403) and drops tracks, so we
build the cache out-of-band here and ship the resulting JSON to the server's
BEATSTER_CATALOG_CACHE path. The server then loads it directly — no live resolve.

Usage:
    uv run python -m tools.build_cache OUT.json [REUSE_CACHE.json]

  OUT.json        where the freshly built cache is written.
  REUSE_CACHE.json (optional) an existing cache whose already-resolved tracks are
                  reused as-is (matched by id) so only genuinely new seeds hit
                  iTunes. Hugely reduces requests on an incremental expansion.

Tunables (env):
  BUILD_CONCURRENCY  parallel requests (default 1 — serial, kindest to iTunes)
  BUILD_PACE_MIN / BUILD_PACE_MAX  random sleep before each request, seconds
                  (default 2.5 / 4.0 → ~15-20 req/min, under iTunes' limit)
  BUILD_PASSES     retry passes over still-failing seeds (default 6)

Strategy: serial + paced requests to stay under the rate limit, then repeated
passes (growing cool-down) over whatever still failed. Any seed that fails every
pass is a genuine resolution problem (bad query / artist mismatch) and is printed
at the end so it can be fixed or dropped.
"""

import asyncio
import json
import os
import random
import sys
import time
from dataclasses import asdict, replace

import httpx

from app.catalog import (
    CACHE_PATH,
    CACHE_VERSION,
    SEED_FILM_TV_TRACKS,
    SEED_TRACKS,
    SEED_TRACKS_DE,
    Track,
    _resolve_track,
    _seed_hash,
    _slug,
)

Job = tuple[str, str, int, str, str | None]  # query, artist, year, category, country

CONCURRENCY = int(os.environ.get("BUILD_CONCURRENCY", "1"))
PACE_S = (
    float(os.environ.get("BUILD_PACE_MIN", "2.5")),
    float(os.environ.get("BUILD_PACE_MAX", "4.0")),
)
MAX_PASSES = int(os.environ.get("BUILD_PASSES", "6"))


def _load_reuse(path: str) -> dict[str, Track]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {t["id"]: Track(**t) for t in data.get("tracks", [])}
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"(could not read reuse cache {path}: {e})", flush=True)
        return {}


async def build(out_path: str, reuse_path: str | None) -> int:
    jobs: list[Job] = (
        [(q, a, y, "music", None) for q, a, y in SEED_TRACKS]
        + [(q, a, y, "music", "DE") for q, a, y in SEED_TRACKS_DE]
        + [(q, a, y, "film_tv", None) for q, a, y in SEED_FILM_TV_TRACKS]
    )
    total = len(jobs)

    resolved: dict[str, Track] = {}
    reuse = _load_reuse(reuse_path) if reuse_path else {}
    todo: list[Job] = []
    for job in jobs:
        prior = reuse.get(_slug(job[0]))
        if prior is not None:
            # reuse only the RESOLUTION (title/artist/preview/artwork); year
            # and category always come from the seed — otherwise a curated
            # year fix would be silently swallowed by the reuse cache
            resolved[prior.id] = replace(prior, year=job[2], category=job[3])
        else:
            todo.append(job)
    print(
        f"seeds {total} | reused {len(resolved)} from cache | to resolve {len(todo)}",
        flush=True,
    )

    sem = asyncio.Semaphore(CONCURRENCY)
    failed: list[Job] = []

    async with httpx.AsyncClient(timeout=20) as client:

        async def one(job: Job, bucket: list[Job]) -> None:
            q, a, y, cat, country = job
            async with sem:
                await asyncio.sleep(random.uniform(*PACE_S))
                t = await _resolve_track(client, q, a, y, cat, country)
            if t is not None:
                resolved[t.id] = t
            else:
                bucket.append(job)

        remaining: list[Job] = todo
        for p in range(MAX_PASSES):
            failed = []
            await asyncio.gather(*(one(j, failed) for j in remaining))
            print(
                f"pass {p + 1}: resolved {len(resolved)}/{total}, "
                f"still failing {len(failed)}",
                flush=True,
            )
            if not failed:
                break
            remaining = failed
            if p < MAX_PASSES - 1:
                cooldown = 15 * (p + 1)
                print(f"  cooling down {cooldown}s before next pass", flush=True)
                await asyncio.sleep(cooldown)

    payload = {
        "version": CACHE_VERSION,
        "seed_hash": _seed_hash(),
        "fetched_at": int(time.time()),
        "tracks": [asdict(t) for t in resolved.values()],
    }
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, out_path)

    print(f"\nwrote {out_path}: {len(resolved)}/{total} tracks", flush=True)
    print(f"version={CACHE_VERSION} seed_hash={_seed_hash()}", flush=True)
    if failed:
        print("\n=== PERMANENTLY UNRESOLVED (fix query/artist or drop) ===")
        for q, a, y, cat, country in sorted(failed, key=lambda j: j[2]):
            print(f"  ({q!r}, {a!r}, {y}, {cat}, country={country})")
    return len(resolved)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else CACHE_PATH
    reuse = sys.argv[2] if len(sys.argv) > 2 else None
    asyncio.run(build(out, reuse))
