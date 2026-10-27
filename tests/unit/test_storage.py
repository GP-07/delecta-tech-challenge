import json

from libs.crawler.storage import append_partial, read_partial, read_venues, write_in_chunks, write_venues


def test_writes_venues_like_the_reference_dataset(tmp_path):
    path = tmp_path / "out" / "venues.json"
    venues = {"1": {"name": "Café Ñandú"}}

    write_venues(path, venues)

    # Same serialisation as just_eat_venues.json: json.dumps defaults (single line, ASCII-escaped).
    assert path.read_text(encoding="utf-8") == json.dumps(venues)
    assert read_venues(path) == venues


def test_write_is_atomic_and_leaves_no_temp_files(tmp_path):
    path = tmp_path / "venues.json"
    write_venues(path, {"1": {}})
    write_venues(path, {"2": {}})

    assert read_venues(path) == {"2": {}}
    assert [path.name for path in tmp_path.iterdir()] == ["venues.json"]


def test_reading_a_missing_file_returns_empty(tmp_path):
    assert read_venues(tmp_path / "nope.json") == {}
    assert read_partial(tmp_path / "nope.jsonl") == {}


def test_partial_results_are_appended_one_venue_per_line(tmp_path):
    path = tmp_path / "venues.partial.jsonl"

    append_partial(path, {"1": {"name": "a"}, "2": {"name": "b"}})
    append_partial(path, {"3": {"name": "c"}})

    assert len(path.read_text(encoding="utf-8").splitlines()) == 3
    assert read_partial(path) == {"1": {"name": "a"}, "2": {"name": "b"}, "3": {"name": "c"}}


class RecordingFile:
    """Remembers every write."""

    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(data)


def test_the_file_is_written_in_large_chunks():
    file = RecordingFile()
    pieces = ['{"', "1", '": ', '{"name": ', '"Caf\\u00e9"', "}", "}"]

    write_in_chunks(file, pieces, size=10)

    assert b"".join(file.writes) == "".join(pieces).encode()
    assert all(len(chunk) >= 10 for chunk in file.writes[:-1])
    assert len(file.writes) < len(pieces)
