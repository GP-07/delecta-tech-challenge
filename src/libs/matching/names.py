"""Name similarity weighted by how distinctive each word is.

Why weights
    "Restaurante Aguila Sushi" and "Sushi" share a word, but "sushi" names hundreds of places in Barcelona: that
    alone proves nothing. Each word weighs its inverse document frequency (IDF) over all the Google names:

        weight(word) = ln((names + 1) / (names with the word + 1)) + 1

    With ~22,000 names, a word in 1 name ("tiflis") weighs ~10.3, one in 44 names ~7.2, and one in 2,000 names
    ("restaurante") ~3.4. A word of the address or of the area (AREA_WORDS) weighs a quarter of that
    (LOCATION_WORD_WEIGHT): in "Popeyes Josep Tarradellas" the venue is "Popeyes", the rest says where it is.

How two names are compared (see matching_business_rules for the word rules)
    1. Each word gets a credit in the other name: 1 if it is there, a partial one for a typo ("napoli"/"nappoli"),
       also when written together or apart ("Mixiang"/"Mi Xiang"), 0 otherwise.
    2. matched weight of a name = Σ weight · credit;  total weight = Σ weight.
    3. containment = max over both names of matched / total: one name inside the other ("Goiko" in "Goiko Grill").
       coverage    = (matched A + matched B) / (total A + total B): how much of both names is shared.
       score       = (containment + coverage) / 2, between 0 and 1.
    4. specific: the names share a distinctive word (one in at most DISTINCTIVE_WORD_SHARE of the names: "goiko"),
       not only common ones ("chino"). conflict: each name has a distinctive word the other lacks.

    Example: "Goiko Grill" vs "GOIKO" -> containment 1 ("goiko" is the whole second name), coverage ~0.72,
    score ~0.86, specific.
"""

import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from libs.matching.constants import AREA_WORDS, DISTINCTIVE_WORD_SHARE, LOCATION_WORD_WEIGHT, NOT_SIMILAR
from libs.matching.domain import NameSimilarity
from libs.matching.matching_business_rules import has_distinctive_word, shares_only_area_words, word_credits
from libs.matching.normalization_business_rules import tokens


@dataclass(frozen=True, slots=True)
class WeightedName:
    """The distinct words of one name, with their weight and their credit in the other name."""

    words: list[str]
    weights: list[float]
    credits: list[float]

    @property
    def matched_weight(self) -> float:
        return sum(weight * credit for weight, credit in zip(self.weights, self.credits, strict=True))

    @property
    def total_weight(self) -> float:
        return sum(self.weights)


class NameComparison:
    """Two weighted names side by side: the measures of the module docstring, one property each."""

    def __init__(self, first: WeightedName, second: WeightedName, distinctive_weight: float) -> None:
        self.first = first
        self.second = second
        self.distinctive_weight = distinctive_weight

    @property
    def containment(self) -> float:
        return max(self.first.matched_weight / self.first.total_weight,
                   self.second.matched_weight / self.second.total_weight)

    @property
    def coverage(self) -> float:
        return ((self.first.matched_weight + self.second.matched_weight)
                / (self.first.total_weight + self.second.total_weight))

    @property
    def is_specific(self) -> bool:
        return has_distinctive_word(self.first.weights, self.first.credits, self.distinctive_weight, shared=True)

    @property
    def has_conflict(self) -> bool:
        return all(has_distinctive_word(name.weights, name.credits, self.distinctive_weight, shared=False)
                   for name in (self.first, self.second))

    def similarity(self) -> NameSimilarity:
        if shares_only_area_words(self.first.words, self.first.credits):
            return NameSimilarity(score=0.0, specific=False, conflict=self.has_conflict)
        return NameSimilarity(score=(self.containment + self.coverage) / 2, specific=self.is_specific,
                              conflict=self.has_conflict)


class NameScorer:
    """Knows how frequent every word is among the target (Google) names, and compares names with those weights."""

    def __init__(self, corpus: Iterable[str]) -> None:
        self._names_with_word: Counter[str] = Counter()
        self._names = 0
        for name in corpus:
            self._names += 1
            self._names_with_word.update(set(tokens(name)))
        # The weight of a word found in DISTINCTIVE_WORD_SHARE of the names: from it on, a word is distinctive.
        self.specific_weight = self._idf(max(1, round(self._names * DISTINCTIVE_WORD_SHARE)))

    def weight(self, word: str) -> float:
        return self._idf(self._names_with_word[word])

    def compare(self, first_name: str, second_name: str, *,
                location_words: frozenset[str] = frozenset()) -> NameSimilarity:
        """`location_words`: words of the addresses of both places, weighed like the area words."""
        first_words, second_words = list(dict.fromkeys(tokens(first_name))), list(dict.fromkeys(tokens(second_name)))
        if not first_words or not second_words:
            return NOT_SIMILAR
        location_words = location_words | AREA_WORDS
        comparison = NameComparison(self._weighted(first_words, second_words, location_words),
                                    self._weighted(second_words, first_words, location_words), self.specific_weight)
        return comparison.similarity()

    def _weighted(self, words: list[str], other_words: list[str], location_words: frozenset[str]) -> WeightedName:
        weights = [self._word_weight(word, location_words) for word in words]
        return WeightedName(words=words, weights=weights, credits=word_credits(words, other_words))

    def _word_weight(self, word: str, location_words: frozenset[str]) -> float:
        weight = self.weight(word)
        return weight * LOCATION_WORD_WEIGHT if word in location_words else weight

    def _idf(self, names_with_word: int) -> float:
        return math.log((self._names + 1) / (names_with_word + 1)) + 1
