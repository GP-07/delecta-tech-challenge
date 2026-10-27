"""Assigns a category of the taxonomy to every menu item: keyword rules first (classification_business_rules), then,
for the items no rule decided, the category of their most similar reference items (embeddings, rule 7).

The references are items the rules decided with high confidence (REFERENCE_CONFIDENCE), in this batch or given by
the caller (e.g. earlier runs). Below LOW_CONFIDENCE a classification is a guess worth reviewing.
"""

import hashlib
from collections import defaultdict
from collections.abc import Sequence

from libs.categorization.classification_business_rules import ItemRuleAnalysis, embedding_confidence
from libs.categorization.constants import (
    MAX_DESCRIPTION_CHARACTERS,
    MIN_SIMILARITY,
    NEIGHBOURS,
    REFERENCE_CONFIDENCE,
    REFERENCES_PER_CATEGORY,
)
from libs.categorization.domain import Classification, MenuItemText, Method, PendingItem
from libs.categorization.embeddings import Embedder, NearestCategories
from libs.categorization.keywords import KeywordRules
from libs.categorization.taxonomy import Taxonomy


def embedding_text(item: MenuItemText) -> str:
    """'Shia Chiao | Entrantes | Empanadillas chinas al vapor': what the embeddings compare."""
    description = " ".join(item.description.split())[:MAX_DESCRIPTION_CHARACTERS]
    return " | ".join(part for part in (item.name, item.section, description) if part)


def stable_order(text: str) -> str:
    """A pseudo-random but fixed order of texts, so every run samples the same references."""
    return hashlib.sha1(text.encode()).hexdigest()  # noqa: S324 - an order, not security


class Classifier:
    """Rules first; with an embedder, the items the rules leave undecided go to their most similar references."""

    def __init__(self, taxonomy: Taxonomy, embedder: Embedder | None = None, *, min_similarity: float = MIN_SIMILARITY,
                 neighbours: int = NEIGHBOURS, references_per_category: int = REFERENCES_PER_CATEGORY):
        self.taxonomy = taxonomy
        self.rules = KeywordRules({category.name for category in taxonomy.categories})
        self.rule_analysis = ItemRuleAnalysis(self.rules, taxonomy)
        self.nearest = NearestCategories(embedder, neighbours) if embedder else None
        self.min_similarity = min_similarity
        self.references_per_category = references_per_category

    def classify(self, items: Sequence[MenuItemText],
                 references: Sequence[tuple[MenuItemText, str]] = ()) -> list[Classification]:
        """`references`: items already classified elsewhere (e.g. earlier runs), with their category name."""
        decided = [self.rule_analysis.decide(item) for item in items]
        pending = [position for position, result in enumerate(decided) if isinstance(result, PendingItem)]
        if self.nearest and pending:
            self._decide_by_embeddings(items, decided, pending, references)
        return [result.final() if isinstance(result, PendingItem) else result for result in decided]

    def _decide_by_embeddings(self, items: Sequence[MenuItemText], decided: list, pending: list[int],
                              references: Sequence[tuple[MenuItemText, str]]) -> None:
        """Rule 7, in place: a pending item takes the category its most similar references vote for, if similar
        enough (min_similarity)."""
        decided_here = [(item, result.category.name) for item, result in zip(items, decided, strict=True)
                        if isinstance(result, Classification) and result.category
                        and result.confidence >= REFERENCE_CONFIDENCE]
        chosen = self._sample([*references, *decided_here])
        texts = [embedding_text(items[position]) for position in pending]
        for position, (category_name, similarity, evidence) in zip(pending, self.nearest.find(texts, chosen),
                                                                   strict=False):
            if similarity >= self.min_similarity:
                decided[position] = Classification(self.taxonomy[category_name], embedding_confidence(similarity),
                                                   Method.EMBEDDING, decided[position].is_combo, evidence)

    def _sample(self, references: Sequence[tuple[MenuItemText, str]]) -> list[tuple[str, str]]:
        """Up to `references_per_category` distinct texts per category, the same ones on every run."""
        texts_by_category: dict[str, set[str]] = defaultdict(set)
        for item, category_name in references:
            if category_name in self.taxonomy:
                texts_by_category[category_name].add(embedding_text(item))
        chosen = []
        for category_name, texts in sorted(texts_by_category.items()):
            ordered = sorted(texts, key=stable_order)
            chosen += [(text, category_name) for text in ordered[:self.references_per_category]]
        return chosen
