from tools.check_years import _base, match_earliest_year


def _rec(title: str, artist: str, date: str) -> dict:
    return {
        "title": title,
        "artist-credit": [{"name": artist}],
        "first-release-date": date,
    }


def test_earliest_matching_year_wins() -> None:
    # remaster/compilation recordings exist too — the earliest plausible one
    # is the original release
    recs = [
        _rec("Bohemian Rhapsody", "Queen", "2011-01-01"),
        _rec("Bohemian Rhapsody", "Queen", "1975-10-31"),
        _rec("Bohemian Rhapsody", "Queen", "1992"),
    ]
    assert match_earliest_year("Bohemian Rhapsody", "Queen", recs) == 1975


def test_wrong_artist_and_title_rejected() -> None:
    recs = [
        _rec("Bohemian Rhapsody", "Panic! At the Disco", "2006-01-01"),
        _rec("Bohemian Like You", "Queen", "1999-01-01"),
    ]
    assert match_earliest_year("Bohemian Rhapsody", "Queen", recs) is None


def test_decorated_titles_and_artists_match_via_base() -> None:
    # iTunes says "Umbrella (feat. JAY-Z)" by "Rihanna feat. JAY-Z";
    # MusicBrainz lists the plain recording by the primary artist
    recs = [_rec("Umbrella", "Rihanna", "2007-03-29")]
    assert (
        match_earliest_year("Umbrella (feat. JAY-Z)", "Rihanna, JAY-Z", recs)
        == 2007
    )


def test_implausible_or_empty_dates_ignored() -> None:
    recs = [
        _rec("Song", "Artist", ""),
        _rec("Song", "Artist", "0000"),
        _rec("Song", "Artist", "1899"),
    ]
    assert match_earliest_year("Song", "Artist", recs) is None


def test_base_strips_decorations() -> None:
    assert _base("Umbrella (feat. JAY-Z)") == "Umbrella"
    assert _base("Stayin' Alive - From Saturday Night Fever") == "Stayin' Alive"
    assert _base("Beyoncé, JAY-Z") == "Beyoncé"
    assert _base("Simon & Garfunkel") == "Simon"
    assert _base("99 Luftballons") == "99 Luftballons"
