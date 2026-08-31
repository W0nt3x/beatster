import asyncio
from typing import Any

import pytest

from app import room as room_module
from app.bingo import (
    CATEGORY_POOL,
    LINES,
    PRESET_ADVANCED,
    PRESET_BEGINNER,
    best_mark_cell,
    bot_answer,
    closest_year_winners,
    evaluate_answer,
    fuzzy_match,
    generate_card,
    has_bingo,
    match_artist,
)
from app.catalog import Track
from app.room import Room, RoomError
from app.schemas import (
    BingoMarksChanged,
    BingoRoundDone,
    BingoRoundResult,
    BingoSpin,
    GameOver,
)

# ---------- pure rules (bingo.py) ----------


def test_generate_card_is_balanced() -> None:
    card = generate_card()
    assert len(card) == 25
    for slot in range(5):
        assert card.count(slot) == 5


def test_has_bingo_lines() -> None:
    assert not has_bingo(set())
    assert has_bingo({0, 1, 2, 3, 4})  # top row
    assert has_bingo({2, 7, 12, 17, 22})  # middle column
    assert has_bingo({0, 6, 12, 18, 24})  # main diagonal
    assert has_bingo({4, 8, 12, 16, 20})  # anti-diagonal
    assert not has_bingo({0, 1, 2, 3, 5})
    assert len(LINES) == 12


def test_presets_are_valid_pool_entries() -> None:
    for preset in (PRESET_BEGINNER, PRESET_ADVANCED):
        assert len(preset) == 5
        assert len(set(preset)) == 5
        assert all(c in CATEGORY_POOL for c in preset)


def test_evaluate_year_categories() -> None:
    y2 = CATEGORY_POOL["year2"]
    assert evaluate_answer(y2, 1985, "T", "A", "1986") == (True, False)
    assert evaluate_answer(y2, 1985, "T", "A", "1985") == (True, True)  # exact
    assert evaluate_answer(y2, 1985, "T", "A", "1988") == (False, False)
    assert evaluate_answer(y2, 1985, "T", "A", "") == (False, False)
    assert evaluate_answer(y2, 1985, "T", "A", "banana") == (False, False)
    # two-digit phone mercy: "85" → 1985, "05" → 2005
    assert evaluate_answer(y2, 1985, "T", "A", "85") == (True, True)
    exact = CATEGORY_POOL["exact"]
    assert evaluate_answer(exact, 2005, "T", "A", "05") == (True, False)
    assert evaluate_answer(exact, 2005, "T", "A", "2004") == (False, False)


def test_evaluate_decade_and_before() -> None:
    dec = CATEGORY_POOL["decade"]
    assert evaluate_answer(dec, 1987, "T", "A", "1980")[0]
    assert not evaluate_answer(dec, 1987, "T", "A", "1990")[0]
    b2k = CATEGORY_POOL["before2000"]
    assert evaluate_answer(b2k, 1999, "T", "A", "before")[0]
    assert not evaluate_answer(b2k, 1999, "T", "A", "after")[0]
    assert evaluate_answer(b2k, 2000, "T", "A", "after")[0]


def test_evaluate_new_year_and_pivot_categories() -> None:
    y1 = CATEGORY_POOL["year1"]
    assert evaluate_answer(y1, 1985, "T", "A", "1986") == (True, False)
    assert evaluate_answer(y1, 1985, "T", "A", "1985") == (True, True)
    assert evaluate_answer(y1, 1985, "T", "A", "1987") == (False, False)
    y5 = CATEGORY_POOL["year5"]
    assert evaluate_answer(y5, 1985, "T", "A", "1990") == (True, False)
    assert evaluate_answer(y5, 1985, "T", "A", "1991") == (False, False)
    b90 = CATEGORY_POOL["before1990"]
    assert evaluate_answer(b90, 1989, "T", "A", "before")[0]
    assert evaluate_answer(b90, 1990, "T", "A", "after")[0]
    b10 = CATEGORY_POOL["before2010"]
    assert evaluate_answer(b10, 2009, "T", "A", "before")[0]
    assert evaluate_answer(b10, 2010, "T", "A", "after")[0]


def test_evaluate_any_text_takes_artist_or_title() -> None:
    cat = CATEGORY_POOL["anytext"]
    assert evaluate_answer(cat, 2004, "Yeah! (feat. Lil Jon)", "USHER", "yeah")[0]
    assert evaluate_answer(cat, 2004, "Yeah! (feat. Lil Jon)", "USHER", "Usher")[0]
    assert evaluate_answer(cat, 2004, "Yeah! (feat. Lil Jon)", "USHER", "Lil Jon")[0]
    assert not evaluate_answer(cat, 2004, "Yeah! (feat. Lil Jon)", "USHER", "Drake")[0]
    assert not evaluate_answer(cat, 2004, "Yeah! (feat. Lil Jon)", "USHER", "")[0]
    # any_text never earns the erase bonus and bots answer it like a title
    assert evaluate_answer(cat, 2004, "T", "A", "T") == (True, False)
    assert bot_answer(cat, 2004, "T", "A", hit=True) == "T"


def test_evaluate_vs_prev() -> None:
    prev = CATEGORY_POOL["prevsong"]
    y = evaluate_answer
    assert y(prev, 1990, "T", "A", "newer", prev_year=1985) == (True, False)
    assert y(prev, 1990, "T", "A", "older", prev_year=1985) == (False, False)
    assert y(prev, 1980, "T", "A", "older", prev_year=1985) == (True, False)
    # dead heat — both sides count
    assert y(prev, 1985, "T", "A", "older", prev_year=1985)[0]
    assert y(prev, 1985, "T", "A", "newer", prev_year=1985)[0]
    # no pivot yet (defensive) or a non-button value → wrong
    assert not y(prev, 1990, "T", "A", "newer")[0]
    assert not y(prev, 1990, "T", "A", "yes", prev_year=1985)[0]


def test_closest_year_winners() -> None:
    # nearest guess wins; unparseable/missing answers never win
    answers: dict[str, str | None] = {
        "a": "1980",
        "b": "1992",
        "c": None,
        "d": "banana",
    }
    assert closest_year_winners(answers, 1985) == {"a"}
    # ties share the win
    assert closest_year_winners({"a": "1980", "b": "1990"}, 1985) == {"a", "b"}
    # nobody answered anything parseable → nobody marks
    assert closest_year_winners({"c": None, "d": "?"}, 1985) == set()
    # a lone answer wins however far off — it's a bet, not a threshold
    assert closest_year_winners({"a": "1950"}, 1985) == {"a"}


def test_bot_answers_new_categories() -> None:
    prev = CATEGORY_POOL["prevsong"]
    assert bot_answer(prev, 1990, "T", "A", hit=True, prev_year=1985) == "newer"
    assert bot_answer(prev, 1990, "T", "A", hit=False, prev_year=1985) == "older"
    assert bot_answer(prev, 1990, "T", "A", hit=True) == ""  # no pivot yet
    closest = CATEGORY_POOL["closest"]
    assert abs(int(bot_answer(closest, 1985, "T", "A", hit=True)) - 1985) <= 2
    assert abs(int(bot_answer(closest, 1985, "T", "A", hit=False)) - 1985) >= 5


def test_artist_matching_accepts_any_credited_name() -> None:
    # THE 2026-07 game-night bug: on all feat-tracks everyone answered the
    # featured guest (it's in the credits!) and was judged wrong
    assert match_artist("Lil Jon", "USHER", "Yeah! (feat. Lil Jon & Ludacris)")
    assert match_artist("Ludacris", "USHER", "Yeah! (feat. Lil Jon & Ludacris)")
    assert match_artist("Usher", "USHER", "Yeah! (feat. Lil Jon & Ludacris)")
    assert match_artist("Young Thug", "Camila Cabello", "Havana (feat. Young Thug)")
    assert match_artist("iann dior", "24kGoldn", "Mood (feat. iann dior)")
    # one name out of a collab credit counts too
    assert match_artist("Marteria", "Marteria, Yasha & Miss Platnum", "Lila Wolken")
    assert match_artist("Miss Platnum", "Marteria, Yasha & Miss Platnum", "Lila Wolken")
    assert match_artist("Daddy Yankee", "Luis Fonsi & Daddy Yankee", "Despacito")
    # wrong artists still fail; title words don't leak into the artist check
    assert not match_artist("Drake", "USHER", "Yeah! (feat. Lil Jon & Ludacris)")
    assert not match_artist("Yeah", "USHER", "Yeah! (feat. Lil Jon & Ludacris)")
    via_eval = evaluate_answer(
        CATEGORY_POOL["artist"], 2004, "Yeah! (feat. Lil Jon & Ludacris)", "USHER", "Lil Jon"
    )
    assert via_eval == (True, False)


def test_fuzzy_matching_is_a_fair_party_judge() -> None:
    # articles, case, accents, feat-tails and brackets don't matter
    assert fuzzy_match("rolling stones", "The Rolling Stones")
    assert fuzzy_match("Grönemeyer", "Gronemeyer")
    assert fuzzy_match("Beyonce", "Beyoncé")
    assert fuzzy_match("africa", "Africa (Live)")
    assert fuzzy_match("Bad Guy", "bad guy (feat. Nobody)")
    assert fuzzy_match("ACDC", "AC/DC")
    # small typos pass, over-specified answers pass
    assert fuzzy_match("Smells Like Teen Spirt", "Smells Like Teen Spirit")
    assert fuzzy_match("Toto Africa", "Africa")
    # half answers do NOT pass
    assert not fuzzy_match("Love", "Love Me Do")
    assert not fuzzy_match("", "Anything")
    assert not fuzzy_match("completely wrong", "Bohemian Rhapsody")


def test_best_mark_cell_advances_a_line() -> None:
    # colour 0 free at cells 4 and 20; row 0 already has 3 marks → cell 4 wins
    card = [0] * 5 + [1] * 5 + [2] * 5 + [3] * 5 + [4] * 4 + [0]
    marks = {0, 1, 2}
    card[24] = 0
    assert best_mark_cell(card, marks, 0) in (3, 4)
    # all colour-0 cells marked → nothing to pick
    assert best_mark_cell(card, {0, 1, 2, 3, 4, 24}, 0) is None


# ---------- room flow ----------


class FakeCatalog:
    def __init__(self, tracks: list[Track]) -> None:
        self.tracks = list(tracks)

    def available_categories(self) -> list[str]:
        return sorted({t.category for t in self.tracks})

    def category_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in self.tracks:
            counts[t.category] = counts.get(t.category, 0) + 1
        return counts

    def has_seed_track(self, track_id: str) -> bool:
        return any(t.id == track_id for t in self.tracks)


@pytest.fixture(autouse=True)
def _no_community_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(room_module, "remember_community_track", lambda _t: None)


@pytest.fixture(autouse=True)
def _no_stats_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(room_module, "record_game_result", lambda **_kw: None)
    monkeypatch.setattr(room_module, "record_placement", lambda **_kw: None)
    monkeypatch.setattr(room_module, "record_activity", lambda *_a, **_kw: None)


@pytest.fixture
def broadcasts() -> list[Any]:
    return []


@pytest.fixture
def destroyed() -> list[bool]:
    return []


@pytest.fixture
def room(broadcasts: list[Any], destroyed: list[bool]) -> Room:
    catalog = FakeCatalog(
        [Track(id="x", title="X", artist="A", year=1970, preview_url="http://x")]
    )

    async def broadcast(msg: Any) -> None:
        broadcasts.append(msg)

    async def on_empty() -> None:
        destroyed.append(True)

    return Room(
        code="TEST",
        catalog=catalog,  # type: ignore[arg-type]
        broadcast=broadcast,
        on_empty=on_empty,
    )


@pytest.fixture
def bingo_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spin fires on the next tick; answer/mark/linger wait for the tests
    (individual tests dial one of them to 0 to exercise the timeout)."""
    monkeypatch.setattr(room_module, "BINGO_SPIN_S", 0)
    monkeypatch.setattr(room_module, "BINGO_ANSWER_S", 60)
    monkeypatch.setattr(room_module, "BINGO_MARK_S", 60)
    monkeypatch.setattr(room_module, "BINGO_LINGER_S", 60)
    # category slot 0 (= year4 in the default beginner preset) every round
    monkeypatch.setattr(room_module.random, "randrange", lambda _n: 0)


def _tracks(n: int) -> list[Track]:
    return [
        Track(
            id=f"t{i}",
            title=f"Song {i}",
            artist=f"Artist {i}",
            year=1985,
            preview_url=f"http://t{i}",
        )
        for i in range(n)
    ]


class _TrackQueue:
    def __init__(self, tracks: list[Track]) -> None:
        self.tracks = list(tracks)
        self.idx = 0

    def pop(self) -> tuple[Track, None, None] | None:
        if self.idx >= len(self.tracks):
            return None
        t = self.tracks[self.idx]
        self.idx += 1
        return (t, None, None)


def _patch_picker(monkeypatch: pytest.MonkeyPatch, tracks: list[Track]) -> None:
    queue = _TrackQueue(tracks)
    monkeypatch.setattr(
        room_module.Room, "_pick_track_no_recycle", lambda self: queue.pop()
    )
    monkeypatch.setattr(room_module.random, "shuffle", lambda lst: None)
    monkeypatch.setattr(room_module.Room, "_eligible_pool_size", lambda self: 50)


async def _tick(n: int = 4) -> None:
    for _ in range(n):
        await asyncio.sleep(0)


async def test_bingo_settings_validation(room: Room) -> None:
    host = await room.add_player("Alice", None)
    other = await room.add_player("Bob", None)

    with pytest.raises(RoomError):
        await room.set_game_mode(other.id, "bingo")
    await room.set_game_mode(host.id, "bingo")
    assert room.game_mode == "bingo"

    with pytest.raises(RoomError):
        await room.set_bingo_categories(host.id, ["year2"])  # not 5
    with pytest.raises(RoomError):
        await room.set_bingo_categories(
            host.id, ["year2", "year2", "year3", "decade", "exact"]  # dupe
        )
    with pytest.raises(RoomError):
        await room.set_bingo_categories(
            host.id, ["year2", "nope", "year3", "decade", "exact"]
        )
    await room.set_bingo_categories(host.id, list(PRESET_ADVANCED))
    assert room.bingo_categories == PRESET_ADVANCED

    with pytest.raises(RoomError):
        await room.set_bingo_answer_seconds(host.id, 5)
    await room.set_bingo_answer_seconds(host.id, 20)
    assert room.bingo_answer_seconds == 20


async def test_bingo_full_round_flow(
    room: Room,
    broadcasts: list[Any],
    bingo_fast: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_picker(monkeypatch, _tracks(12))
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    await room.set_game_mode(p1.id, "bingo")

    await room.start_round(p1.id)
    assert room.state == "bingo_spin"
    assert room.bingo_round == 1
    assert set(room.bingo_cards) == {p1.id, p2.id}
    await _tick()
    assert room.state == "bingo_answering"

    # p1 exact (category year4, track year 1985), p2 misses by 6
    await room.submit_bingo_answer(p1.id, "1985")
    assert room.state == "bingo_answering"  # still waiting for p2
    await room.submit_bingo_answer(p2.id, "1991")
    assert room.state == "bingo_reveal"  # everyone in → early resolve

    result = next(m for m in broadcasts if isinstance(m, BingoRoundResult))
    by_id = {r.player_id: r for r in result.results}
    assert by_id[p1.id].correct and by_id[p1.id].exact
    assert not by_id[p2.id].correct
    # nobody had a mark yet, so the exact hit earns no erase
    assert room._bingo_mark_pending == {p1.id}
    assert not room._bingo_erase_pending

    # wrong-colour cell is rejected, then a legal mark lands
    card = room.bingo_cards[p1.id]
    wrong_cell = card.index(1)
    with pytest.raises(RoomError):
        await room.bingo_mark(p1.id, wrong_cell)
    good_cell = card.index(0)
    await room.bingo_mark(p1.id, good_cell)
    assert room.bingo_marks[p1.id] == {good_cell}
    assert room.cumulative_scores[p1.id] == 1
    assert any(isinstance(m, BingoRoundDone) for m in broadcasts)
    assert room.state == "bingo_reveal"  # lingering before the next spin


async def test_bingo_creative_categories_flow(
    room: Room,
    broadcasts: list[Any],
    bingo_fast: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """closest + prevsong across two rounds: the Zeitduell slot is barred in
    round 1 (no pivot yet), then pivots on the just-revealed song."""
    tracks = [
        Track(id="a", title="First Song", artist="A1", year=1985, preview_url="http://a"),
        Track(id="b", title="Second Song", artist="A2", year=1990, preview_url="http://b"),
        Track(id="c", title="Third Song", artist="A3", year=1970, preview_url="http://c"),
    ]
    _patch_picker(monkeypatch, tracks)
    monkeypatch.setattr(room_module, "BINGO_LINGER_S", 0)
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    await room.set_game_mode(p1.id, "bingo")
    await room.set_bingo_categories(
        p1.id, ["prevsong", "closest", "year2", "decade", "exact"]
    )
    await room.start_round(p1.id)

    # round 1: the pinned randrange picks the FIRST eligible slot — prevsong
    # (slot 0) is excluded without a previous song, so "closest" it is
    assert room.bingo_round == 1
    idx = room._bingo_category_idx
    assert idx is not None and room.bingo_categories[idx] == "closest"
    spin1 = [m for m in broadcasts if isinstance(m, BingoSpin)][-1]
    assert spin1.prev_year is None
    await _tick()

    # 1980 is 5 off, 1992 is 7 off → only the nearer guess marks
    await room.submit_bingo_answer(p1.id, "1980")
    await room.submit_bingo_answer(p2.id, "1992")
    result = [m for m in broadcasts if isinstance(m, BingoRoundResult)][-1]
    by_id = {r.player_id: r for r in result.results}
    assert by_id[p1.id].correct and not by_id[p1.id].exact
    assert not by_id[p2.id].correct
    assert room._bingo_mark_pending == {p1.id}
    await room.bingo_mark(p1.id, room.bingo_cards[p1.id].index(idx))
    await _tick()

    # round 2: the revealed 1985 song is now the Zeitduell pivot
    assert room.bingo_round == 2
    idx2 = room._bingo_category_idx
    assert idx2 is not None and room.bingo_categories[idx2] == "prevsong"
    spin2 = [m for m in broadcasts if isinstance(m, BingoSpin)][-1]
    assert spin2.prev_title == "First Song" and spin2.prev_year == 1985
    await _tick()

    # the 1990 track is newer than 1985
    await room.submit_bingo_answer(p1.id, "newer")
    await room.submit_bingo_answer(p2.id, "older")
    result = [m for m in broadcasts if isinstance(m, BingoRoundResult)][-1]
    by_id = {r.player_id: r for r in result.results}
    assert by_id[p1.id].correct
    assert not by_id[p2.id].correct


async def test_bingo_exact_hit_can_erase(
    room: Room,
    broadcasts: list[Any],
    bingo_fast: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_picker(monkeypatch, _tracks(12))
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    await room.set_game_mode(p1.id, "bingo")
    await room.start_round(p1.id)
    await _tick()

    room.bingo_marks[p2.id] = {7}  # the victim-to-be has one mark
    await room.submit_bingo_answer(p1.id, "1985")  # exact
    await room.submit_bingo_answer(p2.id, "2005")
    assert room._bingo_erase_pending == {p1.id}

    with pytest.raises(RoomError):
        await room.bingo_erase(p1.id, p1.id, 7)  # not your own card
    with pytest.raises(RoomError):
        await room.bingo_erase(p1.id, p2.id, 3)  # cell isn't marked

    await room.bingo_mark(p1.id, room.bingo_cards[p1.id].index(0))
    assert room.state == "bingo_reveal"  # erase still open
    await room.bingo_erase(p1.id, p2.id, 7)
    assert room.bingo_marks[p2.id] == set()
    erased = [
        m for m in broadcasts if isinstance(m, BingoMarksChanged) and m.erased
    ]
    assert erased and erased[-1].player_id == p2.id
    assert erased[-1].actor_id == p1.id
    assert any(isinstance(m, BingoRoundDone) for m in broadcasts)


async def test_bingo_win_ends_the_game(
    room: Room,
    broadcasts: list[Any],
    bingo_fast: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_picker(monkeypatch, _tracks(12))
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    await room.set_game_mode(p1.id, "bingo")
    await room.start_round(p1.id)
    # rig p1: top row is colour 0, four of it already marked
    room.bingo_cards[p1.id] = [0] * 5 + [1] * 5 + [2] * 5 + [3] * 5 + [4] * 5
    room.bingo_marks[p1.id] = {0, 1, 2, 3}
    await _tick()

    await room.submit_bingo_answer(p1.id, "1984")
    await room.submit_bingo_answer(p2.id, "2005")
    await room.bingo_mark(p1.id, 4)

    done = next(m for m in broadcasts if isinstance(m, BingoRoundDone))
    assert done.winners == [p1.id]
    assert room.state == "game_over"
    assert room.bingo_winners == [p1.id]
    assert room.finished_players[0] == p1.id
    over = next(m for m in broadcasts if isinstance(m, GameOver))
    assert over.finished_players[0] == p1.id


async def test_bingo_mark_timeout_auto_picks(
    room: Room,
    broadcasts: list[Any],
    bingo_fast: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(room_module, "BINGO_MARK_S", 0)
    _patch_picker(monkeypatch, _tracks(12))
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    await room.set_game_mode(p1.id, "bingo")
    await room.start_round(p1.id)
    await _tick()

    await room.submit_bingo_answer(p1.id, "1983")
    await room.submit_bingo_answer(p2.id, "2005")
    assert room._bingo_mark_pending == {p1.id}
    await _tick()  # mark timeout fires → auto-pick
    assert len(room.bingo_marks[p1.id]) == 1
    auto = [
        m
        for m in broadcasts
        if isinstance(m, BingoMarksChanged) and m.actor_id is None
    ]
    assert auto and auto[-1].player_id == p1.id
    assert any(isinstance(m, BingoRoundDone) for m in broadcasts)


async def test_bingo_answer_timeout_without_answers(
    room: Room,
    broadcasts: list[Any],
    bingo_fast: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(room_module, "BINGO_ANSWER_S", 0)
    _patch_picker(monkeypatch, _tracks(12))
    p1 = await room.add_player("Alice", None)
    await room.add_player("Bob", None)
    await room.set_game_mode(p1.id, "bingo")
    await room.start_round(p1.id)
    await _tick(6)  # spin → answering → answer timeout → reveal

    assert room.state == "bingo_reveal"
    result = next(m for m in broadcasts if isinstance(m, BingoRoundResult))
    assert all(not r.correct and r.answer == "" for r in result.results)
    assert any(isinstance(m, BingoRoundDone) for m in broadcasts)


async def test_bingo_pool_exhausted_most_marks_wins(
    room: Room,
    broadcasts: list[Any],
    bingo_fast: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(room_module, "BINGO_LINGER_S", 0)
    _patch_picker(monkeypatch, _tracks(1))  # one round, then the pool is dry
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    await room.set_game_mode(p1.id, "bingo")
    await room.start_round(p1.id)
    await _tick()

    await room.submit_bingo_answer(p1.id, "1983")
    await room.submit_bingo_answer(p2.id, "2005")
    await room.bingo_mark(p1.id, room.bingo_cards[p1.id].index(0))
    await _tick(6)  # linger(0) → next round → pool dry → finish

    assert room.state == "game_over"
    assert room.bingo_winners == [p1.id]  # most marks wins the dry-pool case
    assert room.finished_players[0] == p1.id


async def test_bingo_idle_rounds_end_the_game(
    room: Room,
    bingo_fast: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # nobody ever answers (tab left open on the table) — after 3 dead rounds
    # the game ends itself instead of churning through the whole pool
    monkeypatch.setattr(room_module, "BINGO_ANSWER_S", 0)
    monkeypatch.setattr(room_module, "BINGO_LINGER_S", 0)
    _patch_picker(monkeypatch, _tracks(20))
    p1 = await room.add_player("Alice", None)
    await room.add_player("Bob", None)
    await room.set_game_mode(p1.id, "bingo")
    await room.start_round(p1.id)
    for _ in range(40):
        if room.state == "game_over":
            break
        await _tick()
    assert room.state == "game_over"
    assert room.bingo_round == 3  # exactly the idle limit, not the whole pool


async def test_bingo_disconnect_stops_blocking_the_round(
    room: Room,
    bingo_fast: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_picker(monkeypatch, _tracks(12))
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    await room.set_game_mode(p1.id, "bingo")
    await room.start_round(p1.id)
    await _tick()

    await room.submit_bingo_answer(p1.id, "1985")
    assert room.state == "bingo_answering"  # waiting for Bob...
    await room.remove_player(p2.id)  # ...who just left
    assert room.state == "bingo_reveal"  # round resolves without him


async def test_bingo_persist_roundtrip(
    room: Room,
    broadcasts: list[Any],
    destroyed: list[bool],
    bingo_fast: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_picker(monkeypatch, _tracks(12))
    p1 = await room.add_player("Alice", None)
    p2 = await room.add_player("Bob", None)
    await room.set_game_mode(p1.id, "bingo")
    await room.set_bingo_answer_seconds(p1.id, 30)
    await room.start_round(p1.id)
    await _tick()
    await room.submit_bingo_answer(p1.id, "1984")
    await room.submit_bingo_answer(p2.id, "2005")
    await room.bingo_mark(p1.id, room.bingo_cards[p1.id].index(0))
    assert room.state == "bingo_reveal"

    data = room.to_persist()

    async def broadcast(_msg: Any) -> None:
        pass

    async def on_empty() -> None:
        pass

    restored = Room.from_persist(
        data,
        catalog=room._catalog,
        broadcast=broadcast,
        on_empty=on_empty,
    )
    assert restored.state == "bingo_reveal"
    assert restored.game_mode == "bingo"
    assert restored.bingo_answer_seconds == 30
    assert restored.bingo_cards[p1.id] == room.bingo_cards[p1.id]
    assert restored.bingo_marks[p1.id] == room.bingo_marks[p1.id]
    assert restored.bingo_round == 1
    assert restored.last_bingo_result is not None
    assert restored.disconnected == {p1.id, p2.id}
    assert restored._bingo_task is None  # paused until someone reconnects

    await restored.add_player("Alice", p1.id)
    assert restored._bingo_task is not None  # un-paused


async def test_bingo_with_bot(
    room: Room,
    broadcasts: list[Any],
    bingo_fast: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_picker(monkeypatch, _tracks(12))
    monkeypatch.setattr(
        room_module, "BOT_HIT_PROB", {"easy": 1.0, "medium": 1.0, "hard": 1.0}
    )
    monkeypatch.setattr(room_module.random, "uniform", lambda _a, _b: 0.0)
    p1 = await room.add_player("Alice", None)
    bot = await room.add_bot("medium")
    await room.set_game_mode(p1.id, "bingo")
    await room.start_round(p1.id)
    await _tick()
    assert room.state == "bingo_answering"

    await room.submit_bingo_answer(p1.id, "1985")
    await _tick()  # bot answer task fires → everyone in → resolve
    assert room.state == "bingo_reveal"
    result = next(m for m in broadcasts if isinstance(m, BingoRoundResult))
    bot_result = next(r for r in result.results if r.player_id == bot.id)
    assert bot_result.correct  # hit prob forced to 1.0

    await room.bingo_mark(p1.id, room.bingo_cards[p1.id].index(0))
    await _tick()  # bot mark task fires
    assert len(room.bingo_marks[bot.id]) == 1
    assert any(isinstance(m, BingoRoundDone) for m in broadcasts)
