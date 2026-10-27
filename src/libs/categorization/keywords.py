"""Finds the keywords of constants.py in the words of a normalised text (see text_helpers.normalize).

    rules = KeywordRules(taxonomy_category_names)
    rules.hits(["pizza", "barbacoa", "+", "coca", "cola"])
        -> [Hit("pizza", STRONG, start=0, "pizza"), Hit("soft drinks", STRONG, start=3, "coca cola")]

Phrases are found leftmost first and, at each position, the longest one: "coca cola zero" is "coca cola", not
"cola". Found phrases never overlap. A word also matches its plural ("pizza" -> "pizzas", "croqueta" -> "croquetas").
"""

from collections import defaultdict
from dataclasses import dataclass

from libs.categorization.constants import (
    ANCHOR,
    COMBO_SEPARATOR,
    COMBO_WORDS,
    GENERIC_WORDS,
    NON_FOOD_WORDS,
    PLURAL_ENDINGS,
    STRONG_KEYWORDS,
    WEAK_KEYWORDS,
)
from libs.categorization.domain import Hit, Strength
from libs.categorization.text_helpers import normalize


@dataclass(frozen=True, slots=True)
class Phrase:
    words: tuple[str, ...]
    anchored: bool  # only counts at the start of the text
    text: str  # as written in the rules
    value: object  # what a hit of this phrase returns


def singular_forms(word: str) -> list[str]:
    """The word and the singulars it may be the plural of, the word as written first:
    'croquetes' -> ['croquetes', 'croquete', 'croquet'].

    The order decides between two keywords of the same length that match at the same place: the one written as in
    the text wins ("patatas asadas" -> fries, over "patata asada" read as its plural -> other vegetables).
    """
    forms = [word]
    if word.endswith("s"):
        forms.append(word[:-1])
    if word.endswith("es"):
        forms.append(word[:-2])
    return forms


def is_same_word(text_word: str, keyword_word: str) -> bool:
    """The word of the text is the keyword's word, or its plural."""
    return any(text_word == keyword_word + ending for ending in PLURAL_ENDINGS)


def phrase_length(phrase: Phrase) -> int:
    return len(phrase.words)


class PhraseFinder:
    """Finds phrases in a list of words: leftmost first, the longest one at each position, without overlaps."""

    def __init__(self, phrases: dict[str, object]):
        self._phrases_by_first_word: dict[str, list[Phrase]] = defaultdict(list)
        for text, value in phrases.items():
            phrase = Phrase(words=tuple(normalize(text.lstrip(ANCHOR)).split()), anchored=text.startswith(ANCHOR),
                            text=text, value=value)
            self._phrases_by_first_word[phrase.words[0]].append(phrase)
        for candidates in self._phrases_by_first_word.values():
            candidates.sort(key=phrase_length, reverse=True)

    def find(self, words: list[str]) -> list[tuple[int, Phrase]]:
        """(position of its first word, phrase) of every phrase found, in order."""
        found, position = [], 0
        while position < len(words):
            phrase = self._longest_at(words, position)
            if phrase:
                found.append((position, phrase))
                position += len(phrase.words)
            else:
                position += 1
        return found

    def _longest_at(self, words: list[str], position: int) -> Phrase | None:
        longest = None
        for form in singular_forms(words[position]):
            for candidate in self._phrases_by_first_word.get(form, ()):
                if (candidate.anchored and position) or (longest and len(longest.words) >= len(candidate.words)):
                    continue
                if position + len(candidate.words) <= len(words) and all(
                        is_same_word(words[position + offset], keyword_word)
                        for offset, keyword_word in enumerate(candidate.words)):
                    longest = candidate
        return longest


class KeywordRules:
    """Finds the keywords of every category in a text; each hit says where it starts and how strong it is.

    Checked when built: every category of the keywords exists in the taxonomy, and no keyword belongs to two
    categories (an ambiguous word is left out of the rules instead).
    """

    def __init__(self, known_categories: set[str] | frozenset[str]):
        entries: dict[str, tuple[str, Strength]] = {}
        category_of_keyword: dict[str, str] = {}
        for strength, keywords_by_category in ((Strength.STRONG, STRONG_KEYWORDS), (Strength.WEAK, WEAK_KEYWORDS)):
            for category, keywords in keywords_by_category.items():
                if category not in known_categories:
                    raise ValueError(f"rules refer to a category missing from the taxonomy: {category}")
                for keyword in keywords:
                    anchor = ANCHOR if keyword.startswith(ANCHOR) else ""
                    key = anchor + normalize(keyword.lstrip(ANCHOR))
                    if category_of_keyword.setdefault(key, category) != category:
                        raise ValueError(f"keyword {keyword!r} belongs to two categories")
                    entries.setdefault(key, (category, strength))
        self._keywords = PhraseFinder(entries)
        self._non_food = PhraseFinder(dict.fromkeys(NON_FOOD_WORDS, True))
        self._combo = PhraseFinder(dict.fromkeys((*COMBO_WORDS, COMBO_SEPARATOR), True))
        self._generic = PhraseFinder(dict.fromkeys(GENERIC_WORDS, True))

    def hits(self, words: list[str]) -> list[Hit]:
        """Keyword hits of the words of a normalised text, in order of appearance."""
        hits = []
        for start, phrase in self._keywords.find(words):
            category, strength = phrase.value
            hits.append(Hit(category, strength, start, phrase.text))
        return hits

    def is_non_food(self, words: list[str]) -> bool:
        return bool(self._non_food.find(words))

    def is_combo(self, words: list[str]) -> bool:
        return bool(self._combo.find(words))

    def is_generic(self, words: list[str]) -> bool:
        return bool(self._generic.find(words))
