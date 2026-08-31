"""Check curated catalog years against MusicBrainz — report only, no rewrites.

MusicBrainz recordings carry a ``first-release-date``: the ORIGINAL release,
which is exactly what iTunes' remaster/compilation releaseDate is not. This
tool takes a built catalog cache (resolved title/artist/year per track),
queries MusicBrainz for each track and reports every year that disagrees —
plus the tracks it could not find at all. The curated year stays the source
of truth; MB can be wrong too (re-recordings, weird entries), so a human
decides what to change.

Usage (from backend/):
    uv run python -m tools.check_years CACHE.json [--community COMMUNITY.json]
        [--json OUT.json] [--limit N]

MB rate limit is 1 request/second (anonymous) — a full ~475-track catalog
takes ~9 minutes. A meaningful User-Agent with contact info is required by
their policy — set BEATSTER_MB_CONTACT (env or .env) to your email/URL.
"""

import argparse
import asyncio
import json
import re
import sys
import time
from typing import Any

import httpx

from app.config import MB_CONTACT

MB_URL = "https://musicbrainz.org/ws/2/recording"
USER_AGENT = (
    f"beatster-yearcheck/1.0 ({MB_CONTACT or 'set BEATSTER_MB_CONTACT'})"
)
PACE_S = 1.1  # stay under MB's 1 req/s anonymous limit
MAX_PLAUSIBLE = time.gmtime().tm_year + 1
# popular oldies have dozens of live/compilation recordings on MB; a small
# result page often misses the ORIGINAL recording entirely and min() lands on
# a late re-recording. 100 results is still one request.
MB_LIMIT = 100
# resolved titles that carry one of these words while the seed query didn't
# usually mean iTunes handed us a variant SKU instead of the original
_VARIANT_RE = re.compile(
    r"\b(live|remix|rmx|acoustic|session|karaoke|instrumental|cover|"
    r"version|demo|edit)\b",
    re.IGNORECASE,
)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]+", " ", s.lower()).strip()


def _base(s: str) -> str:
    """Title/artist without featuring/version decorations for fuzzy compare."""
    s = re.split(r"\s+[(\[]|\s+-\s+", s)[0]
    s = re.split(
        r"\s*[,&]\s*|\s+(?:feat\.?|featuring|x)\s+", s, flags=re.IGNORECASE
    )[0]
    return s


def _lucene_escape(s: str) -> str:
    return s.replace("\\", r"\\").replace('"', r"\"")


def match_earliest_year(
    title: str, artist: str, recordings: list[dict[str, Any]]
) -> int | None:
    """Earliest plausible first-release year among recordings that actually
    match our title+artist (containment either way, decorations stripped)."""
    want_t, want_tb = _norm(title), _norm(_base(title))
    want_a, want_ab = _norm(artist), _norm(_base(artist))
    years: list[int] = []
    for rec in recordings:
        credit = " ".join(
            c.get("name", "")
            for c in rec.get("artist-credit", [])
            if isinstance(c, dict)
        )
        got_a = _norm(credit)
        if not got_a:
            continue
        if not (
            want_a in got_a
            or got_a in want_a
            or (want_ab and (want_ab in got_a or got_a in want_ab))
        ):
            continue
        got_t = _norm(rec.get("title", ""))
        got_tb = _norm(_base(rec.get("title", "")))
        if got_t != want_t and got_tb != want_tb:
            continue
        raw = (rec.get("first-release-date") or "")[:4]
        if raw.isdigit():
            year = int(raw)
            if 1900 <= year <= MAX_PLAUSIBLE:
                years.append(year)
    return min(years) if years else None


async def _query_mb(
    client: httpx.AsyncClient, title: str, artist: str
) -> list[dict[str, Any]]:
    query = (
        f'recording:"{_lucene_escape(_base(title))}"'
        f' AND artist:"{_lucene_escape(_base(artist))}"'
    )
    for attempt in range(4):
        try:
            r = await client.get(
                MB_URL,
                params={"query": query, "fmt": "json", "limit": MB_LIMIT},
            )
            if r.status_code == 503:  # throttled — back off and retry
                await asyncio.sleep(3 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json().get("recordings", [])
        except httpx.HTTPError:
            if attempt == 3:
                raise
            await asyncio.sleep(3 * (attempt + 1))
    return []


def _load_tracks(path: str, source: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [
        {
            "id": t["id"],
            "title": t["title"],
            "artist": t["artist"],
            "year": int(t["year"]),
            "category": t.get("category", "music"),
            "source": source,
        }
        for t in data.get("tracks", [])
    ]


def resolution_suspects(
    tracks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Offline sanity check: does the resolved title still match its seed?

    The track id is the slug of the seed *query*, so its words should largely
    appear in the resolved title+artist. When they don't, iTunes most likely
    resolved a different song by the same artist (seen in the wild: the E.T.
    seed resolving to the Jurassic Park theme). Separately, variant keywords
    (live/remix/acoustic/…) in the title that the seed never asked for point
    to a wrong SKU whose preview is not the original recording.
    """
    wrong_track: list[dict[str, Any]] = []
    variant_sku: list[dict[str, Any]] = []
    for t in tracks:
        if t["source"] != "seed":
            continue  # community ids are itunes_<number>, nothing to compare
        id_tokens = set(t["id"].split("_"))
        if _looks_like_wrong_track(t["title"], id_tokens):
            wrong_track.append(t)
        for m in _VARIANT_RE.finditer(t["title"]):
            if _norm(m.group(1)) not in id_tokens:
                variant_sku.append(t)
                break
    return wrong_track, variant_sku


_GENERIC_TITLE = {"theme", "main", "title", "song", "intro", "suite", "the", "from"}


def _looks_like_wrong_track(title: str, id_tokens: set[str]) -> bool:
    # compare the undecorated base title (leading parenthetical stripped:
    # "(I Can't Get No) Satisfaction") against the seed-query slug tokens
    base = _base(re.sub(r"^[(\[][^)\]]*[)\]]\s*", "", title))
    tokens = [w for w in _norm(base).split() if len(w) > 1 or w.isdigit()]
    if not tokens:
        return False
    if set(tokens) <= _GENERIC_TITLE:
        # generic 'Theme'-style title: the distinguishing words live in the
        # decorations ('Theme (From "Jurassic Park")') — flag only when NONE
        # of them appear in the seed (catches the E.T.→Jurassic Park case
        # without flagging every long soundtrack subtitle)
        distinct = [
            w
            for w in _norm(title).split()
            if (len(w) > 1 or w.isdigit()) and w not in _GENERIC_TITLE
        ]
        return bool(distinct) and not any(w in id_tokens for w in distinct)
    overlap = sum(1 for w in tokens if w in id_tokens) / len(tokens)
    return overlap < 0.5


async def run(args: argparse.Namespace) -> None:
    tracks = _load_tracks(args.cache, "seed")
    if args.community:
        tracks += _load_tracks(args.community, "community")
    if args.limit:
        tracks = tracks[: args.limit]

    wrong_track, variant_sku = resolution_suspects(tracks)
    print(f"=== RESOLUTION SUSPECTS: WRONG TRACK? ({len(wrong_track)}) ===")
    print("(resolved title barely matches the seed query — iTunes probably")
    print(" picked a different song; fix the seed query and rebuild)")
    for t in wrong_track:
        print(f"  {t['title']} — {t['artist']}  (seed: {t['id']})")
    print(f"\n=== RESOLUTION SUSPECTS: VARIANT SKU? ({len(variant_sku)}) ===")
    print("(live/remix/acoustic wording the seed never asked for — the")
    print(" preview may not be the original recording)")
    for t in variant_sku:
        print(f"  {t['title']} — {t['artist']}  (seed: {t['id']})")

    print(
        f"\nchecking {len(tracks)} tracks against MusicBrainz (~1s each)",
        flush=True,
    )

    mismatches: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    confirmed = 0

    async with httpx.AsyncClient(
        timeout=20, headers={"User-Agent": USER_AGENT}
    ) as client:
        for i, t in enumerate(tracks, 1):
            try:
                recs = await _query_mb(client, t["title"], t["artist"])
            except httpx.HTTPError as e:
                print(f"  ! request failed for {t['title']!r}: {e}")
                unmatched.append({**t, "error": str(e)})
                await asyncio.sleep(PACE_S)
                continue
            mb_year = match_earliest_year(t["title"], t["artist"], recs)
            if mb_year is None:
                unmatched.append(t)
            elif mb_year != t["year"]:
                mismatches.append({**t, "mb_year": mb_year})
            else:
                confirmed += 1
            if i % 25 == 0:
                print(
                    f"  {i}/{len(tracks)} — confirmed {confirmed}, "
                    f"mismatches {len(mismatches)}, no match {len(unmatched)}",
                    flush=True,
                )
            await asyncio.sleep(PACE_S)

    mismatches.sort(key=lambda m: abs(m["mb_year"] - m["year"]), reverse=True)
    music_mm = [m for m in mismatches if m["category"] != "film_tv"]
    film_mm = [m for m in mismatches if m["category"] == "film_tv"]

    def _mm_line(m: dict[str, Any]) -> str:
        diff = m["mb_year"] - m["year"]
        return (
            f"  {diff:+3d}  curated {m['year']}  mb {m['mb_year']}  "
            f"[{m['source']}] {m['title']} — {m['artist']}  ({m['id']})"
        )

    print(f"\n=== MISMATCHES ({len(music_mm)}) — curated vs MusicBrainz ===")
    for m in music_mm:
        print(_mm_line(m))
    print(f"\n=== FILM/TV MISMATCHES ({len(film_mm)}) — usually fine: ===")
    print("(curated year is the film/show year by convention, MB has the")
    print(" recording's release — only act on these if the SHOW year is off)")
    for m in film_mm:
        print(_mm_line(m))
    print(f"\n=== NO MATCH ON MUSICBRAINZ ({len(unmatched)}) — check manually ===")
    for t in unmatched:
        print(f"  {t['year']}  [{t['source']}] {t['title']} — {t['artist']}  ({t['id']})")
    print(f"\n=== CONFIRMED: {confirmed}/{len(tracks)} ===")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "checked": len(tracks),
                    "confirmed": confirmed,
                    "mismatches": music_mm,
                    "film_tv_mismatches": film_mm,
                    "unmatched": unmatched,
                    "wrong_track_suspects": wrong_track,
                    "variant_sku_suspects": variant_sku,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
        print(f"report written to {args.json}")


def main() -> None:
    # Windows consoles default to cp1252 — track titles are full of characters
    # outside it, so force UTF-8 (with replacement as a last resort)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", help="built catalog cache JSON to verify")
    parser.add_argument("--community", help="community_tracks.json to include")
    parser.add_argument("--json", help="also write a JSON report here")
    parser.add_argument("--limit", type=int, help="only check the first N")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
