import hashlib
from pathlib import Path

from apps.pipeline.constants import HASH_BLOCK_BYTES


def file_sha256(path: Path) -> str:
    """SHA-256 of a run's input file, read in blocks so a large file is never loaded whole."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        while block := file.read(HASH_BLOCK_BYTES):
            digest.update(block)
    return digest.hexdigest()
