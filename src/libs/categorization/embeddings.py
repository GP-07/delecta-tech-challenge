"""Text embeddings for the items no rule decides: an item takes the category of its most similar reference items.

The references are items the rules already classified with high confidence, so an unseen dish ("Shia Chiao",
"Chaulafán") is compared with real dishes of the menus, in their own words.

The model runs locally (ONNX, fastembed): menus are never sent to a third party. It is loaded from a folder
prepared when the image is built (a pinned revision); it is never downloaded while the pipeline runs.
"""

from collections import Counter
from collections.abc import Sequence
from typing import Protocol

import numpy as np

from libs.categorization.constants import EMBEDDING_BATCH_SIZE, NEIGHBOURS


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> np.ndarray:
        """One L2-normalised vector per text."""


class FastEmbedder:
    def __init__(self, model_name: str, model_path: str, batch_size: int = EMBEDDING_BATCH_SIZE):
        from fastembed import TextEmbedding  # heavy import: only when embeddings are used

        self._model = TextEmbedding(model_name, specific_model_path=model_path, local_files_only=True)
        self._batch_size = batch_size

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        vectors = np.array(list(self._model.embed(list(texts), batch_size=self._batch_size)), dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.where(norms == 0, 1, norms)


class NearestCategories:
    """Vote of the k most similar references, each weighted by its similarity."""

    def __init__(self, embedder: Embedder, neighbours: int = NEIGHBOURS):
        self._embedder = embedder
        self._neighbours = neighbours

    def find(self, texts: Sequence[str], references: Sequence[tuple[str, str]]) -> list[tuple[str, float, str]]:
        """(category, similarity of the most similar reference, that reference) for each text."""
        if not texts or not references:
            return []
        similarities = self._embedder.embed(texts) @ self._embedder.embed([text for text, _ in references]).T
        neighbours = min(self._neighbours, len(references))
        nearest = np.argsort(-similarities, axis=1)[:, :neighbours]  # per text, its most similar references first
        found = []
        for text_position, reference_positions in enumerate(nearest):
            votes: Counter[str] = Counter()
            for reference_position in reference_positions:
                votes[references[reference_position][1]] += float(similarities[text_position, reference_position])
            category = votes.most_common(1)[0][0]
            best = next(position for position in reference_positions if references[position][1] == category)
            found.append((category, float(similarities[text_position, best]), references[best][0]))
        return found
