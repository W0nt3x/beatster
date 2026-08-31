from pathlib import Path

import pytest

from app import stats
from app.stats import PlayerResult


@pytest.fixture(autouse=True)
def _tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stats, "DB_PATH", str(tmp_path / "test.db"))
    stats.init_db()


def _pr(name: str, **kw: object) -> PlayerResult:
    defaults: dict = dict(
        is_bot=False,
        place=None,
        final_cards=3,
        correct=2,
        wrong=1,
        steals_won=0,
        steal_attempts=0,
    )
    defaults.update(kw)
    return PlayerResult(name=name, **defaults)


def test_record_and_leaderboard_aggregation() -> None:
    # game 1: Alice wins over Bob
    stats.record_game_result(
        room_code="AAAAAA",
        card_target=10,
        singleplayer=False,
        players=[
            _pr("Alice", place=1, correct=5, steals_won=1, steal_attempts=2),
            _pr("Bob", place=2, correct=3),
        ],
    )
    # game 2: same people, different name casing — must merge by norm_name
    stats.record_game_result(
        room_code="BBBBBB",
        card_target=10,
        singleplayer=False,
        players=[_pr("alice", place=2), _pr("Bob", place=1)],
    )

    board = stats.leaderboard()
    assert [r["wins"] for r in board] == [1, 1]
    by_name = {str(r["name"]).lower(): r for r in board}
    alice = by_name["alice"]
    assert alice["games"] == 2
    assert alice["podiums"] == 2
    assert alice["correct"] == 5 + 2
    assert alice["steals_won"] == 1
    assert alice["name"] == "alice"  # latest spelling wins

    t = stats.totals()
    assert t == {"games_recorded": 2, "multiplayer_games": 2}


def test_leaderboard_excludes_bots_and_singleplayer() -> None:
    # singleplayer game: human beats bots — recorded, but not ranked
    stats.record_game_result(
        room_code="SOLO01",
        card_target=10,
        singleplayer=True,
        players=[
            _pr("Loner", place=1),
            _pr("Ada", is_bot=True, place=2),
        ],
    )
    # multiplayer game with a bot participating
    stats.record_game_result(
        room_code="MULTI1",
        card_target=10,
        singleplayer=False,
        players=[
            _pr("Alice", place=1),
            _pr("Bob", place=2),
            _pr("Turing", is_bot=True),
        ],
    )
    board = stats.leaderboard()
    names = {str(r["name"]) for r in board}
    assert names == {"Alice", "Bob"}  # no bots, no solo player
    assert stats.totals() == {"games_recorded": 2, "multiplayer_games": 1}


def test_record_never_raises_on_db_trouble(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stats, "DB_PATH", "Z:/definitely/not/writable/x.db")
    # must swallow the error — a stats hiccup must never break game over
    stats.record_game_result(
        room_code="X", card_target=10, singleplayer=False, players=[_pr("A")]
    )
    stats.record_placement(**_placement("A", "t1", 1999))
    stats.record_activity("room_created", "AAAAAA", {"bots": 0})


# ---------- placements + owner activity ----------


def _placement(
    name: str, track_id: str, year: int, **kw: object
) -> dict:
    defaults: dict = dict(
        room_code="AAAAAA",
        kind="turn",
        name=name,
        is_bot=False,
        singleplayer=False,
        track_id=track_id,
        title=f"Title {track_id}",
        artist="Artist",
        year=year,
        correct=False,
        timed_out=False,
        off_by=3,
    )
    defaults.update(kw)
    return defaults


def test_owner_summary_aggregates() -> None:
    stats.record_activity("room_created", "AAAAAA", {"bots": 0})
    stats.record_activity("search", None, {"q": "nirvana", "results": 5})
    stats.record_activity("search", None, {"q": "obscure song", "results": 0})
    stats.record_activity(
        "game_started", "AAAAAA", {"players": ["Alice", "Bob"]}
    )

    # "hard": 3 human turn attempts, 0 hits -> hardest track
    for _ in range(3):
        stats.record_placement(**_placement("Alice", "hard", 1971))
    # "easy": 3 human turn attempts, all hits
    for _ in range(3):
        stats.record_placement(
            **_placement("Bob", "easy", 1999, correct=True, off_by=0)
        )
    # bot + steal attempts are stored but excluded from the fun aggregates
    stats.record_placement(**_placement("Ada", "hard", 1971, is_bot=True))
    stats.record_placement(**_placement("Bob", "hard", 1971, kind="steal"))
    # only 2 attempts -> below the >=3 threshold for hardest_tracks
    stats.record_placement(**_placement("Alice", "rare", 1985))
    stats.record_placement(**_placement("Bob", "rare", 1985))

    s = stats.owner_summary()
    totals = s["totals"]
    assert isinstance(totals, dict)
    assert totals["placements"] == 10
    assert totals["activity_events"] == 4

    hardest = s["hardest_tracks"]
    assert isinstance(hardest, list)
    assert [t["title"] for t in hardest] == ["Title hard", "Title easy"]
    assert hardest[0] == {
        "title": "Title hard",
        "artist": "Artist",
        "year": 1971,
        "attempts": 3,
        "hits": 0,
    }

    decades = s["decade_hit_rate"]
    assert decades == [
        {"decade": 1970, "attempts": 3, "hits": 0},
        {"decade": 1980, "attempts": 2, "hits": 0},
        {"decade": 1990, "attempts": 3, "hits": 3},
    ]

    zero = s["zero_result_searches"]
    assert isinstance(zero, list)
    assert len(zero) == 1
    assert zero[0]["q"] == "obscure song"
    assert zero[0]["times"] == 1

    per_day = s["per_day"]
    assert isinstance(per_day, list)
    today = per_day[-1]
    assert today["placements"] == 10
    assert today["search"] == 2
    assert today["game_started"] == 1

    recent = s["recent_activity"]
    assert isinstance(recent, list)
    assert recent[0]["type"] == "game_started"  # newest first
    assert recent[0]["detail"] == {"players": ["Alice", "Bob"]}


def test_owner_token_check(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import _owner_token_ok

    monkeypatch.delenv("HITSTER_OWNER_TOKEN", raising=False)
    # no token configured -> endpoint stays off, nothing matches
    assert not _owner_token_ok("")
    assert not _owner_token_ok("anything")
    monkeypatch.setenv("HITSTER_OWNER_TOKEN", "s3cret")
    assert _owner_token_ok("s3cret")
    assert not _owner_token_ok("wrong")
    assert not _owner_token_ok("")
