"""What the classification rules can read about one menu item (see classification_business_rules).

Every rule receives the same ItemContext and reads only what it needs. Each piece of data is computed the first
time a rule asks for it, and only once: a new rule that needs new data adds a property here, without changing the
constructor nor the other rules.
"""

from functools import cached_property

from libs.categorization.constants import CONNECTORS, ENTREES
from libs.categorization.domain import Hit, MenuItemText, Strength
from libs.categorization.keywords import KeywordRules
from libs.categorization.taxonomy import Category, Taxonomy
from libs.categorization.text_helpers import words


def head_end(name_words: list[str]) -> int:
    """Index of the first word after the head of a dish name (all of them when it has no connector):
    'pollo asado con patatas' -> 2 ('pollo asado' is the dish, 'con patatas' its side)."""
    return next((position for position, word in enumerate(name_words) if position > 0 and word in CONNECTORS),
                len(name_words))


def first_hit(hits: list[Hit], strength: Strength) -> Hit | None:
    """The first hit of that strength: in a name the first word decides ("Flan de té verde" is a flan)."""
    return next((hit for hit in hits if hit.strength == strength), None)


class ItemContext:
    def __init__(self, item: MenuItemText, keywords: KeywordRules, taxonomy: Taxonomy) -> None:
        self.item = item
        self.keywords = keywords
        self.taxonomy = taxonomy

    # --- words --------------------------------------------------------------------------------------------

    @cached_property
    def name_words(self) -> list[str]:
        return words(self.item.name)

    @cached_property
    def section_words(self) -> list[str]:
        return words(self.item.section)

    @cached_property
    def description_words(self) -> list[str]:
        return words(self.item.description)

    # --- what the item is ---------------------------------------------------------------------------------

    @cached_property
    def is_combo(self) -> bool:
        """'Menú 3', 'Pizza + bebida', or any item of a 'Menús' section."""
        return self.keywords.is_combo(self.name_words) or self.keywords.is_combo(self.section_words)

    @cached_property
    def is_generic(self) -> bool:
        """'Postre del día', 'Surtido de entrantes': the item does not name a concrete dish."""
        return self.keywords.is_generic(self.name_words)

    @cached_property
    def is_non_food(self) -> bool:
        return self.keywords.is_non_food(self.name_words)

    # --- keyword hits -------------------------------------------------------------------------------------

    @cached_property
    def name_hits(self) -> list[Hit]:
        return self.keywords.hits(self.name_words)

    @cached_property
    def head_hits(self) -> list[Hit]:
        """Hits in the head of the name, before its first connector: 'Pollo asado' of 'Pollo asado + Coca-Cola'."""
        name_head_end = head_end(self.name_words)
        return [hit for hit in self.name_hits if hit.start < name_head_end]

    @cached_property
    def tail_hits(self) -> list[Hit]:
        """Hits in the rest of the name: 'Coca-Cola' of 'Pollo asado + Coca-Cola'."""
        name_head_end = head_end(self.name_words)
        return [hit for hit in self.name_hits if hit.start >= name_head_end]

    @cached_property
    def description_head_hits(self) -> list[Hit]:
        description_head_end = head_end(self.description_words)
        return [hit for hit in self.keywords.hits(self.description_words) if hit.start < description_head_end]

    @cached_property
    def section_hits(self) -> list[Hit]:
        return self.keywords.hits(self.section_words)

    @cached_property
    def best_section_hit(self) -> Hit | None:
        """The most precise strong hit of the section that is not a course: a course ("Entrantes", "Tapas") as a
        section says little about the dish, so only the weak-section fallback uses it."""
        strong_hits = [hit for hit in self.section_hits if self.category(hit).parent != ENTREES]
        return self.most_precise_hit(strong_hits, Strength.STRONG)

    # --- helpers ------------------------------------------------------------------------------------------

    def category(self, hit: Hit) -> Category:
        return self.taxonomy[hit.category]

    def most_precise_hit(self, hits: list[Hit], strength: Strength) -> Hit | None:
        """The hit of that strength with the most precise category, then the first: in a section a precise
        category goes first ("Vinos Blancos": blancos, not generic wines)."""
        candidates = [hit for hit in hits if hit.strength == strength]
        return min(candidates, key=self._precision_order) if candidates else None

    def _precision_order(self, hit: Hit) -> tuple[bool, int]:
        return self.category(hit).is_generic_or_other, hit.start
