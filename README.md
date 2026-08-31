# Beatster

A self-hosted realtime music party game for your friends' game nights:
a song snippet plays, everyone guesses where it belongs in time. Browser-based,
no accounts, no app: players join with a name and a 6-character room code.

Two game modes:

- **Classic** (Hitster-style timeline play): hear a mystery song, place it
  between the years you've already collected. First to the card target wins.
  With an optional steal race when someone places wrong.
- **Music Bingo** (simultaneous rounds on 5×5 colour cards): a category wheel
  picks the round's question (year ±N, decade, artist, title, "older or newer
  than the last song?", closest-guess-wins, …), everyone answers at once,
  correct answers mark cells. First full row/column/diagonal wins.

UI in **German and English** (auto-detected, toggleable). Dark neon-club look.

## Features

- Realtime multiplayer over WebSockets, server-authoritative: no client ever
  sees the answer early
- AI opponents with three difficulty levels (plus a dedicated singleplayer mode)
- Players can add songs to the pool mid-lobby (with preview listening and a
  per-player cap); contributions persist and grow the catalog
- Host-tunable rules: card target, starting cards, snippet/guess/steal timers,
  stealing on/off, bingo categories (15-category pool, ordered picks = board
  colours), audio mode
- **Couch mode**: sound only on the host device (one shared screen / TV),
  or online mode where every device plays
- Reconnect grace, offline badges, host migration, and checkpoint persistence:
  a server restart mid-game resumes at the last reveal
- Persistent career leaderboard (SQLite, identity = player name, multiplayer
  games only)
- Installable as a PWA; open tabs auto-update after a deploy
- DiceBear avatars (pick your emoji face; bots are robots)

## How it works

```
Browser (React) <-- WebSocket --> FastAPI (one async process) <--HTTPS--> iTunes Search API
                                        |
                          in-memory rooms + JSON/SQLite state files
```

- **Backend:** Python 3.12, FastAPI, native WebSockets. Rooms live in memory;
  finished-game stats go to a small SQLite file; the song catalog is a
  pre-built JSON cache. No external services, no Redis, no Postgres: one
  process is plenty for game-night scale.
- **Frontend:** React 19 + Vite + TypeScript + Tailwind v4, hand-rolled
  router/i18n, built to static files.
- **Audio:** Apple's public iTunes Search API provides 30-second preview
  clips (no auth, CORS-friendly). See the legal note below.

## Quick start (Docker)

```sh
git clone <this repo> beatster && cd beatster
docker compose up --build
# open http://localhost:8000
```

That's it: the image builds the frontend, serves everything from one
process, and seeds the bundled song-catalog cache into the `./data` volume on
first start. Player-added songs, stats and room snapshots land in `./data`
too; back that folder up and you've backed up everything.

## Quick start (manual)

Requirements: Python 3.12 + [uv](https://docs.astral.sh/uv/), Node 22 + pnpm.

```sh
# 1. build the frontend
cd frontend && pnpm install && pnpm build && cd ..

# 2. install backend deps
cd backend && uv sync

# 3. put the bundled catalog cache where the server looks for it
mkdir -p ~/.cache/hitster && cp ../data/catalog.json ~/.cache/hitster/

# 4. run: one process serves API, WebSockets and the built frontend
BEATSTER_STATIC_DIR=../frontend/dist uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For development use two processes with hot reload instead: `make dev` runs
uvicorn (`:8000`) and the Vite dev server (`:5173`, proxies `/api` + `/ws`).

## Playing with friends: where to run it

Everyone joins through the browser, so the only requirement is that all
players can reach the server:

- **Same room, same Wi-Fi:** run it on your PC (Docker or manual, see above)
  and friends open `http://<your-LAN-IP>:8000` on their phones. Docker
  publishes port 8000 on all interfaces, nothing else to set up. Switch the
  room to **couch mode** (host-only sound) so the music comes from the one
  device on the TV or speaker instead of six phones at once.
- **Friends elsewhere (Discord night):** the server has to be reachable from
  the internet. The clean way is a small VPS or cloud box with a domain and
  a reverse proxy (Caddy or nginx) in front of port 8000 that terminates
  HTTPS and forwards WebSockets. The quick-and-dirty way is port forwarding
  on your home router to the PC running it: works, but exposes your home
  IP, stays plain HTTP unless you add a proxy, and rides on your upload
  bandwidth. Leave the room in **online mode** so every device plays the
  snippet, or stay in couch mode and share the host's audio in your voice
  channel.
- HTTPS is not strictly required (the game runs fine over plain HTTP on a
  LAN), but the PWA "add to home screen" install needs it and browsers warn
  on plain-HTTP pages, so a shared internet link should have it.

There are no accounts: anyone with the URL and a 6-character room code can
join. Keep the address within your circle, and read the legal note below
before exposing an instance to strangers.

## Configuration

Everything is env vars with sane defaults; see [`.env.example`](.env.example)
for the full annotated list. The short version:

| Variable | Default | What it does |
| --- | --- | --- |
| `BEATSTER_DATA_DIR` | `~/.cache/hitster` | One base dir for all mutable state |
| `BEATSTER_CATALOG_CACHE` | `<data dir>/catalog.json` | Pre-built seed catalog |
| `BEATSTER_DB` | `<data dir>/hitster.db` | SQLite stats/leaderboard DB |
| `BEATSTER_ROOMS_DIR` | `<data dir>/rooms` | Room checkpoint snapshots |
| `BEATSTER_STATIC_DIR` | *(unset)* | Serve the built frontend from FastAPI |
| `BEATSTER_OWNER_TOKEN` | *(unset = off)* | Enables `GET /api/owner/summary` |
| `BEATSTER_MB_CONTACT` | *(unset)* | Contact for the MusicBrainz year-check tool |

(Each variable is also honored under a legacy `HITSTER_*` spelling, and some
internal identifiers and default paths still use the project's historical
working name; they're not user-facing.)

## The song catalog

**Curation is the game design.** The pool is ~475 tracks spanning the 1960s to
today, defined as seed tuples in `backend/app/catalog.py`:

```python
("Yeah Usher", "Usher", 2004),   # (search query, expected artist, curated year)
```

The **curated year is the source of truth**: iTunes' `releaseDate` is often
a remaster/compilation year, so every seed carries a manually verified
original-release year.

- **A pre-built catalog cache ships in [`data/`](data/)** so you don't have to
  resolve anything to get playing.
- **Changing the seeds?** Rebuild the cache with
  `cd backend && uv run python -m tools.build_cache out.json`. It resolves
  seeds against the iTunes API politely (token bucket, multiple passes).
  Expect a full rebuild to take a while; that's deliberate. **Never** let a
  server live-resolve hundreds of tracks at boot: Apple rate-limits per IP
  (~20 requests/min) and a burst gets your IP temporarily blocked.
- **Verifying years:** `uv run python -m tools.check_years CACHE.json` checks
  every curated year against MusicBrainz' first-release-date and reports
  mismatches (report only, a human decides). Set `BEATSTER_MB_CONTACT` first.
- **Player-added songs** are resolved via iTunes search at add-time, stored in
  `community_tracks.json` next to the cache, and merged into the pool on every
  start.

The in-game search is submit-only and rate-capped server-side for the same
reason: several players typing at once must not get your IP blocked.

## Nice to know

- **Custom avatars:** drop `avatar-*.png` files into `frontend/src/avatars/`
  and they appear in the avatar picker. Meme faces of your friend group
  recommended.
- The catalog leans German/international (it was curated for a German friend
  group), so fork the seed lists to match your crowd; that's the point.

## Legal note (read this before hosting)

This repository contains **no music**, only facts (titles, artists, years)
and code. At runtime, *your* instance plays 30-second preview clips fetched
directly from Apple's public iTunes preview CDN.

This project is built for **private game nights among friends**. Think of it
like the printed cards of a music quiz that you play in your living room.
Hosting a publicly accessible instance for strangers is a different story:
depending on your jurisdiction, playing preview clips in a public web offering
may require licenses that neither this project nor Apple's preview API grant
you. That responsibility is yours.

Not affiliated with, endorsed by, or connected to Apple, Jumbo, or the
Hitster board game. "Hitster" is a trademark of its owner; this project's
internal identifiers use the word only historically.

## License

[MIT](LICENSE)
