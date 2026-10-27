"""Downloads the embedding model used to categorize menu items, at a pinned revision, and checks every file.

Usage: python src/libs/categorization/download_model.py [destination]
       (default destination: data/downloads/embedding_model)

Run when the Docker image is built (or once on a laptop); the pipeline then loads the folder with
CATEGORIZATION_EMBEDDING_MODEL_PATH and never downloads anything. A file whose SHA-256 differs from the pinned one
is a tampered or different model: the folder is deleted and the script fails.

It imports nothing of the project, so the Docker image runs it on its own, before copying the code: a code change
does not download the model again.
"""

import hashlib
import shutil
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

REPOSITORY = "Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"  # what fastembed uses for this model
REVISION = "faf4aa4225822f3bc6376869cb1164e8e3feedd0"  # 2024-07-15
SHA256 = {
    "config.json": "c8ec081fdad2df991bf5abbf18418fec7a5cdaa421f60ffb060a30040b8c376f",
    "model_optimized.onnx": "634d0f66c29dc934c8fa72b8a4fe91dd4d420a22f1d82a241058d4316e659a99",
    "ort_config.json": "99881c45e073696289224931dd48694398bc6bcd1fe7cb7018bca1e0cc00e1fc",
    "special_tokens_map.json": "8c785abebea9ae3257b61681b4e6fd8365ceafde980c21970d001e834cf10835",
    "tokenizer.json": "fa685fc160bbdbab64058d4fc91b60e62d207e8dc60b9af5c002c5ab946ded00",
    "tokenizer_config.json": "0666eebf692422757e1dddf3c9fb1ded73ba3dc726c5828671fc89e45bf3609f",
    "unigram.json": "da145b5e7700ae40f16691ec32a0b1fdc1ee3298db22a31ea55f57a966c4a65d",
}
DEFAULT_DESTINATION = Path(__file__).resolve().parents[3] / "data" / "downloads" / "embedding_model"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DESTINATION
    snapshot_download(REPOSITORY, revision=REVISION, local_dir=destination, allow_patterns=list(SHA256))
    wrong = [name for name, expected in SHA256.items() if sha256(destination / name) != expected]
    if wrong:
        shutil.rmtree(destination)
        sys.exit(f"checksum mismatch for {wrong}: model deleted")
    shutil.rmtree(destination / ".cache", ignore_errors=True)
    print(f"model {REPOSITORY}@{REVISION[:7]} ready in {destination}")


if __name__ == "__main__":
    main()
