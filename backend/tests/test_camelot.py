import pytest

from app.domain.camelot import CamelotKey


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("8A", "8A"),
        ("11b", "11B"),
        ("Am", "8A"),
        ("A#m", "3A"),
        ("Bbm", "3A"),
        ("F#", "2B"),
        ("Gb", "2B"),
        ("Dbm", "12A"),
        ("Abmin", "1A"),
        ("E", "12B"),
        ("Cb", "1B"),
        ("Fm", "4A"),
        ("F", "7B"),
    ],
)
def test_parse(text: str, expected: str) -> None:
    assert str(CamelotKey.parse(text)) == expected


def test_from_pitch_matches_spotify_convention() -> None:
    # Spotify / Essentia : 0 = Do ; Fa mineur = 5 -> 4A
    assert str(CamelotKey.from_pitch(5, minor=True)) == "4A"
    assert str(CamelotKey.from_pitch(0, minor=False)) == "8B"


@pytest.mark.parametrize(
    ("key", "parallel"),
    [("4A", "7B"), ("7B", "4A"), ("6A", "9B"), ("11A", "2B"), ("2B", "11A")],
)
def test_parallel_swaps_mode_keeps_tonic(key: str, parallel: str) -> None:
    # Les erreurs Essentia observées : TESLA / Von dutch 4A <-> 7B, Losing It 6A <-> 9B
    assert str(CamelotKey.parse(key).parallel()) == parallel


@pytest.mark.parametrize("bad", ["13A", "0B", "H", "8C", ""])
def test_invalid(bad: str) -> None:
    with pytest.raises(ValueError):
        CamelotKey.parse(bad)
