"""Bingo mode — the pure rules, testable without sockets or timers.

Adapted from the physical bingo board (2026-07 design decision): instead of
a fixed board side A/B the host picks 5 categories from a pool (presets map to
the physical sides; "group or solo?" is deferred until MusicBrainz artist-type
enrichment exists and is replaced by a second year category). Everyone answers
every round simultaneously; a correct answer marks one cell of the drawn
category's colour on the player's 5x5 card; first full row/column/diagonal
wins. An EXACT year hit on a ±N category additionally erases one opponent
mark (the side-A spice rule).

This module holds: the category pool, answer evaluation (including the fuzzy
text matching for artist/title), card generation, the win check, and the
small strategy heuristics shared by bots and the auto-pick timeout.
"""

import random
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

# Category kinds and what the client renders for them:
#   year_range  — numeric year input; correct within ±tolerance, an EXACT hit
#                 additionally earns an erase (the only kind that does)
#   exact_year  — numeric year input; only the exact year counts
#   decade      — decade picker (client sends any year of the decade)
#   before_year — two buttons: "before" / "after" the pivot year
#   artist      — free text, fuzzy-matched against any credited artist
#                 (incl. feat.-guests from the title — see artist_candidates)
#   title       — free text, fuzzy-matched against the track title
#   any_text    — free text; artist OR title counts (the easy social one)
#   vs_prev     — two buttons: "older" / "newer" than the PREVIOUS round's
#                 song (just revealed, so a fresh public pivot every round;
#                 not drawable in round 1 — see the room's slot filter)
#   closest_year— numeric year input; only the player(s) nearest the truth
#                 mark (ties share) — resolved via closest_year_winners,
#                 NOT per-player evaluate_answer


@dataclass(frozen=True, slots=True)
class BingoCategory:
    id: str
    kind: str
    tolerance: int = 0  # year_range only
    pivot: int = 2000  # before_year only


CATEGORY_POOL: dict[str, BingoCategory] = {
    c.id: c
    for c in (
        BingoCategory("year1", "year_range", tolerance=1),
        BingoCategory("year2", "year_range", tolerance=2),
        BingoCategory("year3", "year_range", tolerance=3),
        BingoCategory("year4", "year_range", tolerance=4),
        BingoCategory("year5", "year_range", tolerance=5),
        BingoCategory("decade", "decade"),
        BingoCategory("before1990", "before_year", pivot=1990),
        BingoCategory("before2000", "before_year", pivot=2000),
        BingoCategory("before2010", "before_year", pivot=2010),
        BingoCategory("exact", "exact_year"),
        BingoCategory("artist", "artist"),
        BingoCategory("title", "title"),
        BingoCategory("anytext", "any_text"),
        BingoCategory("prevsong", "vs_prev"),
        BingoCategory("closest", "closest_year"),
    )
}

# The order of the host's 5 picks assigns the five board colours
# (slot 0..4 = yellow, green, violet, cyan, pink — like the physical board).
# The presets mirror the physical sides; beginner slot 1 was "group or solo?"
# on the board and is ±3 here until the MusicBrainz enrichment lands.
PRESET_BEGINNER = ["year4", "year3", "decade", "year2", "before2000"]
PRESET_ADVANCED = ["artist", "title", "decade", "year3", "exact"]

BOARD_SIZE = 5
CARD_CELLS = BOARD_SIZE * BOARD_SIZE

# all 12 winning lines (5 rows, 5 columns, 2 diagonals) as cell-index sets
LINES: list[frozenset[int]] = (
    [frozenset(r * BOARD_SIZE + c for c in range(BOARD_SIZE)) for r in range(BOARD_SIZE)]
    + [frozenset(r * BOARD_SIZE + c for r in range(BOARD_SIZE)) for c in range(BOARD_SIZE)]
    + [
        frozenset(i * BOARD_SIZE + i for i in range(BOARD_SIZE)),
        frozenset(i * BOARD_SIZE + (BOARD_SIZE - 1 - i) for i in range(BOARD_SIZE)),
    ]
)


def generate_card(rng: random.Random | None = None) -> list[int]:
    """A 25-cell card: each cell holds a colour slot 0..4, five of each,
    shuffled — every player gets a different distribution (strategy!)."""
    cells = [slot for slot in range(BOARD_SIZE) for _ in range(BOARD_SIZE)]
    (rng or random).shuffle(cells)
    return cells


def has_bingo(marks: set[int]) -> bool:
    return any(line <= marks for line in LINES)


# ---------- answer evaluation ----------


def _parse_year(raw: str) -> int | None:
    m = re.search(r"\d{1,4}", raw)
    if m is None:
        return None
    year = int(m.group())
    if year < 100:  # "87" → 1987, "05" → 2005 (phone-keyboard mercy)
        year += 1900 if year >= 40 else 2000
    if not 1000 <= year <= 2100:
        return None
    return year


_BRACKETS_RE = re.compile(r"[(\[].*?[)\]]")
_FEAT_RE = re.compile(r"\b(feat|ft|featuring)\b.*")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_ARTICLES = frozenset(
    {"the", "a", "an", "der", "die", "das", "den", "le", "la", "les", "los", "el"}
)


def normalize_text(s: str) -> str:
    """Fold a title/artist (or a guess at one) to a comparable core: lowercase,
    de-accented, brackets and feat.-tails dropped, articles removed."""
    s = s.lower().replace("ß", "ss").replace("$", "s").replace("&", " and ")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = _BRACKETS_RE.sub(" ", s)
    s = _FEAT_RE.sub(" ", s)
    s = _NON_ALNUM_RE.sub(" ", s)
    words = [w for w in s.split() if w not in _ARTICLES]
    return " ".join(words) if words else s.strip()


def fuzzy_match(guess: str, target: str) -> bool:
    """Is the free-text guess close enough? Deliberately a party-game judge:
    forgiving about typos and extra words, strict about half answers
    ("Love" must not count for "Love Me Do")."""
    g, t = normalize_text(guess), normalize_text(target)
    if not g or not t:
        return False
    if g == t:
        return True
    target_words = set(t.split())
    if target_words and target_words <= set(g.split()):
        return True  # over-specified guess ("toto africa" for "africa") is fine
    return SequenceMatcher(None, g, t).ratio() >= 0.8


# Feat.-guests usually live in the TITLE ("Yeah! (feat. Lil Jon & Ludacris)"),
# not the artist field — pull them out before normalize_text() strips them.
_FEAT_CLAUSE_RE = re.compile(
    r"\b(?:feat\.?|ft\.?|featuring)\s+([^()\[\]]+)", re.IGNORECASE
)
# splits a credit list ("A, B & C", "A x B") into the individual names
_ARTIST_SPLIT_RE = re.compile(
    r"\s*(?:,|&|\+|\bfeat\.?\b|\bft\.?\b|\bfeaturing\b|\bx\b|\bvs\.?\b"
    r"|\band\b|\bund\b|\bwith\b|\bmit\b)\s*",
    re.IGNORECASE,
)


def artist_candidates(artist: str, title: str) -> list[str]:
    """Every name that should count as "the artist": the credit string itself,
    feat.-guests hiding in the title, and each individual name split out of a
    collab list. Party-game friendliness (2026-07 game-night lesson: everyone
    answered "Lil Jon" for Yeah! and was judged wrong): naming ANY credited
    artist is a hit. Knowingly lax for duo band names ("Garfunkel" counts)."""
    sources = [artist, *_FEAT_CLAUSE_RE.findall(f"{artist} {title}")]
    out: list[str] = []
    seen: set[str] = set()
    for src in sources:
        for name in (src, *_ARTIST_SPLIT_RE.split(src)):
            name = name.strip(" .-")
            key = normalize_text(name) if name else ""
            if key and key not in seen:
                seen.add(key)
                out.append(name)
    return out


def match_artist(guess: str, artist: str, title: str) -> bool:
    return any(fuzzy_match(guess, cand) for cand in artist_candidates(artist, title))


def closest_year_winners(
    raw_by_player: dict[str, str | None], year: int
) -> set[str]:
    """closest_year is a bet, not a threshold: whoever is nearest the truth
    marks, however far off — ties share the win. Unparseable/missing answers
    never win; nobody answering means nobody marks."""
    dists: dict[str, int] = {}
    for pid, raw in raw_by_player.items():
        if raw is None:
            continue
        guess = _parse_year(raw)
        if guess is not None:
            dists[pid] = abs(guess - year)
    if not dists:
        return set()
    best = min(dists.values())
    return {pid for pid, d in dists.items() if d == best}


def evaluate_answer(
    cat: BingoCategory,
    year: int,
    title: str,
    artist: str,
    raw: str,
    prev_year: int | None = None,
) -> tuple[bool, bool]:
    """-> (correct, exact_bonus). The bonus (erase an opponent mark) only
    exists on year_range categories, per the physical side-A rule.
    closest_year is NOT handled here (it needs everyone's answers at once —
    use closest_year_winners); this returns False for it defensively."""
    raw = raw.strip()
    if not raw:
        return False, False
    if cat.kind == "year_range":
        guess = _parse_year(raw)
        if guess is None:
            return False, False
        return abs(guess - year) <= cat.tolerance, guess == year
    if cat.kind == "exact_year":
        return _parse_year(raw) == year, False
    if cat.kind == "decade":
        guess = _parse_year(raw)
        if guess is None:
            return False, False
        return guess // 10 == year // 10, False
    if cat.kind == "before_year":
        want = "before" if year < cat.pivot else "after"
        return raw == want, False
    if cat.kind == "vs_prev":
        if prev_year is None or raw not in ("older", "newer"):
            return False, False
        if year == prev_year:
            return True, False  # dead heat — both sides count
        want = "older" if year < prev_year else "newer"
        return raw == want, False
    if cat.kind == "artist":
        return match_artist(raw, artist, title), False
    if cat.kind == "title":
        return fuzzy_match(raw, title), False
    if cat.kind == "any_text":
        return fuzzy_match(raw, title) or match_artist(raw, artist, title), False
    return False, False


def bingo_off_by(cat: BingoCategory, raw: str | None, year: int) -> int | None:
    """Years off, for the stats DB — only meaningful for numeric categories."""
    numeric = ("year_range", "exact_year", "decade", "closest_year")
    if raw is None or cat.kind not in numeric:
        return None
    guess = _parse_year(raw)
    return abs(guess - year) if guess is not None else None


# ---------- bot + auto-pick strategy ----------


def bot_answer(
    cat: BingoCategory,
    year: int,
    title: str,
    artist: str,
    hit: bool,
    rng: random.Random | None = None,
    prev_year: int | None = None,
) -> str:
    """The bot knows the truth server-side; `hit` (rolled from BOT_HIT_PROB)
    decides whether it answers correctly or plausibly wrong."""
    r = rng or random
    if cat.kind == "year_range":
        if hit:
            return str(year + r.randint(-cat.tolerance, cat.tolerance))
        miss = cat.tolerance + r.randint(1, 6)
        return str(year + miss * r.choice((-1, 1)))
    if cat.kind == "exact_year":
        return str(year) if hit else str(year + r.choice((-3, -2, -1, 1, 2, 3)))
    if cat.kind == "decade":
        decade = year // 10 * 10
        return str(decade) if hit else str(decade + r.choice((-10, 10)))
    if cat.kind == "before_year":
        want = "before" if year < cat.pivot else "after"
        if hit:
            return want
        return "after" if want == "before" else "before"
    if cat.kind == "vs_prev":
        if prev_year is None:
            return ""
        want = "older" if year < prev_year else "newer"
        if hit:
            return want
        return "newer" if want == "older" else "older"
    if cat.kind == "closest_year":
        # a hitting bot lands close but not reliably exact (an exact guess
        # would also steal the erase bonus every time)
        off = r.randint(-2, 2) if hit else r.choice((-9, -7, -6, 5, 6, 8))
        return str(year + off)
    if cat.kind == "artist":
        return artist if hit else ""
    # title / any_text — a missing bot just "didn't know it"
    return title if hit else ""


def best_mark_cell(card: list[int], marks: set[int], slot: int) -> int | None:
    """The free cell of `slot`'s colour that best advances a line — used by
    bots and by the timeout auto-pick (so dozing off still helps you)."""
    candidates = [
        i for i in range(CARD_CELLS) if card[i] == slot and i not in marks
    ]
    if not candidates:
        return None

    def score(cell: int) -> int:
        return max(
            (len(line & marks) for line in LINES if cell in line), default=0
        )

    return max(candidates, key=score)


def best_erase(
    marks_by_player: dict[str, set[int]], exclude: str
) -> tuple[str, int] | None:
    """The most dangerous opponent mark: one sitting in the fullest line."""
    best: tuple[str, int] | None = None
    best_score = -1
    for pid, marks in marks_by_player.items():
        if pid == exclude or not marks:
            continue
        for line in LINES:
            hit_cells = line & marks
            if hit_cells and len(hit_cells) > best_score:
                best_score = len(hit_cells)
                best = (pid, next(iter(hit_cells)))
    return best
