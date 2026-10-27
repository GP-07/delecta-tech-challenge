import json
import os
import tempfile
from pathlib import Path

from libs.crawler.constants import WRITE_CHUNK_BYTES


def write_venues(path: Path, venues: dict) -> None:
    """Writes {restaurant_id: venue} like just_eat_venues.json, atomically.

    The file is written next to the target and renamed into place, so an interrupted write never leaves a
    truncated JSON behind. The JSON is encoded piece by piece (the whole text would double the memory) and
    written in large chunks.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(file_descriptor, "wb", buffering=0) as temporary_file:
            write_in_chunks(temporary_file, json.JSONEncoder().iterencode(venues), WRITE_CHUNK_BYTES)
            os.fsync(temporary_file.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def write_in_chunks(file, parts, size: int) -> None:
    """Joins the small text pieces of `parts` into writes of at least `size` bytes (the last one may be smaller)."""
    pending, length = [], 0
    for part in parts:
        pending.append(part)
        length += len(part)
        if length >= size:
            file.write("".join(pending).encode("utf-8"))
            pending, length = [], 0
    if pending:
        file.write("".join(pending).encode("utf-8"))


def read_venues(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def append_partial(path: Path, venues: dict) -> None:
    """Appends venues to a JSON Lines file, one {restaurant_id: venue} per line.

    Appending keeps saving progress cheap: each batch writes only its own venues, instead of rewriting
    everything crawled so far (~200 MB for the full list).
    """
    with Path(path).open("a", encoding="utf-8") as file:
        for restaurant_id, venue in venues.items():
            file.write(json.dumps({restaurant_id: venue}) + "\n")
        file.flush()
        os.fsync(file.fileno())


def read_partial(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    venues = {}
    with path.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                venues.update(json.loads(line))
    return venues
