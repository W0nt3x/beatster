from pathlib import Path

import pytest

from app import catalog as catalog_module
from app.catalog import Catalog, Track, clean_title


def _track(id: str, year: int) -> Track:
    return Track(
        id=id, title=id.upper(), artist="X", year=year, preview_url=f"http://{id}"
    )


class _FakeResp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def get(self, url: str, params: dict | None = None) -> _FakeResp:
        return _FakeResp(self._payload)


def _hit(title: str, artist: str, year: int, kind: str = "song") -> dict:
    return {
        "kind": kind,
        "trackName": title,
        "artistName": artist,
        "releaseDate": f"{year}-01-01T00:00:00Z",
    }


async def test_earliest_release_year_picks_original() -> None:
    payload = {
        "results": [
            _hit("Bohemian Rhapsody (2011 Remaster)", "Queen", 2011),
            _hit("Bohemian Rhapsody", "Queen", 1975),
            # different artist — filtered
            _hit("Bohemian Rhapsody", "Panic! At the Disco", 2016),
            # live version keeps its suffix — title mismatch, filtered
            _hit("Bohemian Rhapsody (Live)", "Queen", 1986),
            # implausible year — filtered
            _hit("Bohemian Rhapsody", "Queen", 1492),
        ]
    }
    year = await catalog_module._earliest_release_year(
        _FakeClient(payload),  # type: ignore[arg-type]
        "Bohemian Rhapsody (2011 Remaster)",
        "Queen",
        2011,
    )
    assert year == 1975


async def test_earliest_release_year_falls_back_without_matches() -> None:
    payload = {"results": [_hit("Other Song", "Queen", 1980)]}
    year = await catalog_module._earliest_release_year(
        _FakeClient(payload),  # type: ignore[arg-type]
        "Bohemian Rhapsody",
        "Queen",
        2011,
    )
    assert year == 2011


async def test_earliest_release_year_falls_back_on_http_error() -> None:
    import httpx

    class _ErrClient:
        async def get(self, url: str, params: dict | None = None) -> _FakeResp:
            raise httpx.ConnectError("boom")

    year = await catalog_module._earliest_release_year(
        _ErrClient(),  # type: ignore[arg-type]
        "Bohemian Rhapsody",
        "Queen",
        2011,
    )
    assert year == 2011


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Don't Stop Believin' (2024 Remaster)", "Don't Stop Believin'"),
        ("Africa (Remastered)", "Africa"),
        ("Hotel California [2013 Remaster]", "Hotel California"),
        ("Wonderwall - Remastered", "Wonderwall"),
        ("Imagine - 2010 Remaster", "Imagine"),
        ("Yesterday (Remastered 2009)", "Yesterday"),
        # meaningful suffixes stay untouched
        ("Layla (Live)", "Layla (Live)"),
        ("Plain Title", "Plain Title"),
        # never return an empty string
        ("(Remastered)", "(Remastered)"),
    ],
)
def test_clean_title(raw: str, expected: str) -> None:
    assert clean_title(raw) == expected


def test_cache_roundtrip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache_file = tmp_path / "cat.json"
    monkeypatch.setattr(catalog_module, "CACHE_PATH", str(cache_file))

    tracks = [_track("a", 1985), _track("b", 2010)]
    catalog_module._save_cache(tracks)
    assert cache_file.exists()
    loaded = catalog_module._load_cache()
    assert loaded == tracks


def test_cache_invalidates_on_seed_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache_file = tmp_path / "cat.json"
    monkeypatch.setattr(catalog_module, "CACHE_PATH", str(cache_file))

    catalog_module._save_cache([_track("a", 1985)])

    original = list(catalog_module.SEED_TRACKS)
    monkeypatch.setattr(
        catalog_module,
        "SEED_TRACKS",
        original + [("New Song NewArtist", "NewArtist", 2024)],
    )
    assert catalog_module._load_cache() is None


def test_cache_invalidates_on_ttl_expiry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache_file = tmp_path / "cat.json"
    monkeypatch.setattr(catalog_module, "CACHE_PATH", str(cache_file))
    monkeypatch.setattr(catalog_module, "CACHE_TTL_S", 0)

    catalog_module._save_cache([_track("a", 1985)])
    # any positive elapsed time exceeds TTL=0
    import time as _t
    _t.sleep(0.01)
    assert catalog_module._load_cache() is None


def test_cache_returns_none_when_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache_file = tmp_path / "missing.json"
    monkeypatch.setattr(catalog_module, "CACHE_PATH", str(cache_file))
    assert catalog_module._load_cache() is None


def test_cache_returns_none_when_corrupt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache_file = tmp_path / "corrupt.json"
    cache_file.write_text("{not valid json")
    monkeypatch.setattr(catalog_module, "CACHE_PATH", str(cache_file))
    assert catalog_module._load_cache() is None


def test_itunes_rate_limiter_caps_burst(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # reset the bucket to a known full state, then drain it
    monkeypatch.setattr(catalog_module, "_ITUNES_BURST", 6.0)
    monkeypatch.setattr(catalog_module, "_itunes_tokens", 6.0)
    monkeypatch.setattr(catalog_module, "_itunes_last_refill", __import__("time").monotonic())
    # the first BURST calls pass, the next is capped (refill in-between is negligible)
    allowed = sum(1 for _ in range(6) if catalog_module._itunes_rate_ok())
    assert allowed == 6
    assert catalog_module._itunes_rate_ok() is False


def test_community_track_roundtrip_and_merge(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    comm = tmp_path / "community_tracks.json"
    monkeypatch.setattr(catalog_module, "COMMUNITY_PATH", str(comm))
    t1 = Track(id="itunes_1", title="One", artist="A", year=1999, preview_url="http://1")
    catalog_module.remember_community_track(t1)
    # re-adding the same id overwrites (dedup), not duplicates
    t1b = Track(id="itunes_1", title="One v2", artist="A", year=1999, preview_url="http://1b")
    catalog_module.remember_community_track(t1b)
    loaded = catalog_module._load_community()
    assert len(loaded) == 1 and loaded[0].title == "One v2"
    # _merge_community folds them into the live pool by id
    cat = catalog_module.Catalog()
    cat._tracks = [Track(id="seed", title="S", artist="B", year=1980, preview_url="http://s")]
    cat._merge_community()
    ids = {t.id for t in cat.tracks}
    assert ids == {"seed", "itunes_1"}


def test_detect_category_film_vs_music() -> None:
    f = catalog_module._detect_category
    # genre signal
    assert f("Soundtracks", "Some Album") == "film_tv"
    assert f("Filmmusik", "") == "film_tv"
    # collection signal even when genre is generic
    assert f("Pop", "Dr. No (Original Motion Picture Soundtrack)") == "film_tv"
    assert f("Klassik", "Inception (Music from the Motion Picture)") == "film_tv"
    assert f("Soundtracks", "Breaking Bad (Music from the Original TV Series)") == "film_tv"
    # normal songs stay music
    assert f("Pop", "After Hours") == "music"
    assert f("Hip-Hop/Rap", "2sad2disco") == "music"
    assert f("Schlager", "Party Hits") == "music"
    assert f("", "") == "music"
