from dataclasses import dataclass
from enum import IntEnum, StrEnum

from libs.categorization.taxonomy import Category


class Method(StrEnum):
    """What decided the category of an item."""

    NAME = "name"
    SECTION = "section"
    DESCRIPTION = "description"
    EMBEDDING = "embedding"
    NON_FOOD = "non_food"
    UNKNOWN = "unknown"


class Strength(IntEnum):
    WEAK = 1  # an ingredient ("pollo"): decides only when no strong keyword does
    STRONG = 2  # a kind of dish ("pizza"): decides on its own


@dataclass(frozen=True, slots=True)
class MenuItemText:
    name: str
    section: str = ""
    description: str = ""


@dataclass(frozen=True, slots=True)
class Hit:
    """A keyword found in a text."""

    category: str
    strength: Strength
    start: int  # index of its first word
    keyword: str


@dataclass(frozen=True, slots=True)
class Classification:
    category: Category | None
    confidence: float
    method: Method
    is_combo: bool
    evidence: str  # the keyword or the most similar text that decided it


@dataclass(frozen=True, slots=True)
class PendingItem:
    """An item no rule decided before the embeddings; `fallback` is its weak-section category, if any."""

    fallback: Classification | None
    is_combo: bool

    def final(self) -> Classification:
        """What the item gets when the embeddings do not decide it either."""
        return self.fallback or Classification(None, 0.0, Method.UNKNOWN, self.is_combo, "")
