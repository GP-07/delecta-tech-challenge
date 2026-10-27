"""Which rule decides the category of a menu item, and with what confidence. The keywords and the confidences are
in constants.py; what a rule can read about an item, in item_context.py.

Every rule is a function of its own: it receives the item's context and returns a Classification, or None when it
does not apply. `classification_rules()` lists them in order, and the first that applies decides:

    rule                                                                     example                     confidence
    1. strong_name_keyword: a strong keyword in the head of its name         "Pizza Barbacoa"            0.95
       (the head ends at the first connector: "Pollo asado | + Coca-Cola")
    2. non_food_word: a non-food word in its name, no category               "Palillos"                  0.90
    3. specific_section: a specific strong keyword in its menu section       "Carbonara" in "Pizzas"     0.85
    4. weak_name_keyword: a weak keyword (an ingredient) in its name's head  "Pollo al curry" (chicken)  0.75
    5. rest_of_name: a keyword in the rest of its name                       "Eristoff, 50ml - Vodka"    0.65
    5b. generic_section: a generic strong keyword in its menu section        "Coca-Cola" in "Bebidas"    0.85
    6. combo_description: for a combo, a keyword in its description's head   "Menú 3": "3 dürüm + ..."   0.60
    7. (classifier.py) the vote of its most similar items, by embeddings     "Shia Chiao"                0.5 x simil.
    8. weak_section: a weak section, only when nothing else decided          "Entrantes", "Tapas"        0.40

Rule 7 compares all the undecided items of a batch at once, so it is not a rule of one item: it runs in the
classifier, between the rules and the weak-section fallback.

To add a rule: write a function `(ItemContext) -> Classification | None` and put it in `classification_rules()`
at its place. If it needs data the context does not have yet, add a property to ItemContext.

Two refinements, shared by the rules:
    - A section more precise than the name wins in rule 1: "Mushroom Rice" (generic rice) in "Platos Biryani" (other
      rice) is "other rice".
    - A category found in the section becomes its "other" sibling when the item is a concrete dish: "Tamer" in
      "Postres" is "other sweets", while "Postre del día" stays "generic sweets".
"""

from collections.abc import Callable

from libs.categorization.constants import (
    COMBO_DESCRIPTION_CONFIDENCE,
    EMBEDDING_WEIGHT,
    NON_FOOD_CONFIDENCE,
    OTHER_PREFIX,
    REST_OF_NAME_CONFIDENCE,
    SECTION_CONFIDENCE,
    STRONG_NAME_CONFIDENCE,
    WEAK_NAME_CONFIDENCE,
    WEAK_SECTION_CONFIDENCE,
)
from libs.categorization.domain import Classification, Hit, MenuItemText, Method, PendingItem, Strength
from libs.categorization.item_context import ItemContext, first_hit
from libs.categorization.keywords import KeywordRules
from libs.categorization.taxonomy import Taxonomy

ClassificationRule = Callable[[ItemContext], Classification | None]

# --- the rules, in order ---------------------------------------------------------------------------------------


def strong_name_keyword(context: ItemContext) -> Classification | None:
    """1. "Pizza Barbacoa" is a pizza. A more precise section wins: "Mushroom Rice" in "Platos Biryani"."""
    hit = first_hit(context.head_hits, Strength.STRONG)
    if hit is None:
        return None
    section_hit = context.best_section_hit
    if section_hit and section_refines_name(context, hit, section_hit):
        return classify_as(context, section_hit, STRONG_NAME_CONFIDENCE, Method.SECTION)
    return classify_as(context, hit, STRONG_NAME_CONFIDENCE, Method.NAME)


def non_food_word(context: ItemContext) -> Classification | None:
    """2. Chopsticks, bags, delivery fees: on the menu, but neither food nor drink."""
    if not context.is_non_food:
        return None
    return Classification(None, NON_FOOD_CONFIDENCE, Method.NON_FOOD, context.is_combo,
                          " ".join(context.name_words))


def specific_section(context: ItemContext) -> Classification | None:
    """3. "Carbonara" in "Pizzas" is a pizza: a section with a specific category names the dish."""
    hit = context.best_section_hit
    if hit is None or context.category(hit).is_generic_or_other:
        return None
    return classify_as(context, hit, SECTION_CONFIDENCE, Method.SECTION, from_section=True)


def weak_name_keyword(context: ItemContext) -> Classification | None:
    """4. "Pollo al curry" is chicken: an ingredient in the head of the name, when no dish word is there."""
    hit = first_hit(context.head_hits, Strength.WEAK)
    return classify_as(context, hit, WEAK_NAME_CONFIDENCE, Method.NAME) if hit else None


def rest_of_name(context: ItemContext) -> Classification | None:
    """5. "Eristoff, 50ml - Vodka" is a spirit: a keyword after the head of the name."""
    hit = first_hit(context.tail_hits, Strength.STRONG) or first_hit(context.tail_hits, Strength.WEAK)
    return classify_as(context, hit, REST_OF_NAME_CONFIDENCE, Method.NAME) if hit else None


def generic_section(context: ItemContext) -> Classification | None:
    """5b. "Coca-Cola" in "Bebidas": a section with a generic category. After rules 4 and 5, so "Eristoff, 50ml -
    Vodka" there is a spirit, not just a drink."""
    hit = context.best_section_hit
    return classify_as(context, hit, SECTION_CONFIDENCE, Method.SECTION, from_section=True) if hit else None


def combo_description(context: ItemContext) -> Classification | None:
    """6. "Menú 3": the description of a combo says what it is ("3 dürüm + patatas + Coca-Cola")."""
    if not context.is_combo:
        return None
    hits = context.description_head_hits
    hit = first_hit(hits, Strength.STRONG) or first_hit(hits, Strength.WEAK)
    return classify_as(context, hit, COMBO_DESCRIPTION_CONFIDENCE, Method.DESCRIPTION) if hit else None


def weak_section(context: ItemContext) -> Classification | None:
    """8. The fallback when neither the rules nor the embeddings decided: any keyword of the section, courses
    included ("Entrantes", "Tapas", "Pollo")."""
    hit = (context.most_precise_hit(context.section_hits, Strength.STRONG)
           or context.most_precise_hit(context.section_hits, Strength.WEAK))
    return classify_as(context, hit, WEAK_SECTION_CONFIDENCE, Method.SECTION, from_section=True) if hit else None


def classification_rules() -> tuple[ClassificationRule, ...]:
    """The rules of one item, in order: the first that returns a classification decides."""
    return (strong_name_keyword, non_food_word, specific_section, weak_name_keyword, rest_of_name,
            generic_section, combo_description)


def embedding_confidence(similarity: float) -> float:
    """7. An item decided by its most similar references is never surer than half their similarity."""
    return round(EMBEDDING_WEIGHT * similarity, 3)


# --- shared by the rules ---------------------------------------------------------------------------------------


def classify_as(context: ItemContext, hit: Hit, confidence: float, method: Method,
                from_section: bool = False) -> Classification:
    """The classification a hit gives. From the section, a concrete dish gets the "other" sibling of the category:
    "Tamer" in "Postres" is "other sweets"."""
    category = context.category(hit)
    if from_section and not context.is_generic:
        category = context.taxonomy.sibling(category, OTHER_PREFIX) or category
    return Classification(category, confidence, method, context.is_combo, hit.keyword)


def section_refines_name(context: ItemContext, name_hit: Hit, section_hit: Hit) -> bool:
    """'Mushroom Rice' (generic rice) in 'Platos Biryani' (other rice): the section is more precise."""
    name_category, section_category = context.category(name_hit), context.category(section_hit)
    return (name_category.is_generic and not section_category.is_generic
            and name_category.parent == section_category.parent)


# --- the analysis ----------------------------------------------------------------------------------------------


class ItemRuleAnalysis:
    """Applies the rules to items: the first rule that applies decides; when none does, the item is pending (the
    embeddings get a chance) with the weak-section fallback."""

    def __init__(self, keywords: KeywordRules, taxonomy: Taxonomy) -> None:
        self.keywords = keywords
        self.taxonomy = taxonomy
        self.rules = classification_rules()

    def decide(self, item: MenuItemText) -> Classification | PendingItem:
        context = ItemContext(item, self.keywords, self.taxonomy)
        for rule in self.rules:
            classification = rule(context)
            if classification is not None:
                return classification
        return PendingItem(fallback=weak_section(context), is_combo=context.is_combo)
