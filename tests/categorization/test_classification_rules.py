"""Each classification rule on its own: what it decides when it applies, and that it stays out when it does not."""

import pytest

from libs.categorization import classification_business_rules as business_rules
from libs.categorization.domain import MenuItemText, Method, PendingItem
from libs.categorization.item_context import ItemContext
from libs.categorization.keywords import KeywordRules
from libs.categorization.taxonomy import read_taxonomy
from tests.categorization.test_taxonomy import TAXONOMY

TAXONOMY_CATEGORIES = read_taxonomy(TAXONOMY)
KEYWORDS = KeywordRules({category.name for category in TAXONOMY_CATEGORIES.categories})


def context(name, section="", description=""):
    return ItemContext(MenuItemText(name, section, description), KEYWORDS, TAXONOMY_CATEGORIES)


def outcome(classification):
    return classification and (classification.category and classification.category.name, classification.method,
                               classification.confidence)


@pytest.mark.parametrize(("rule", "item", "expected"), [
    (business_rules.strong_name_keyword, context("Pizza Barbacoa"), ("pizza", Method.NAME, 0.95)),
    (business_rules.strong_name_keyword, context("Mushroom Rice", "Platos Biryani"),
     ("other rice", Method.SECTION, 0.95)),
    (business_rules.non_food_word, context("Palillos"), (None, Method.NON_FOOD, 0.9)),
    (business_rules.specific_section, context("Carbonara", "Pizzas"), ("pizza", Method.SECTION, 0.85)),
    (business_rules.weak_name_keyword, context("Pollo al curry"), ("chicken", Method.NAME, 0.75)),
    (business_rules.rest_of_name, context("Eristoff, 50ml - Vodka"), ("other espirituosas", Method.NAME, 0.65)),
    (business_rules.generic_section, context("Tamer", "Postres"), ("other sweets", Method.SECTION, 0.85)),
    (business_rules.combo_description, context("Menú 3", description="3 dürüm + patatas"),
     ("kebab", Method.DESCRIPTION, 0.6)),
    (business_rules.weak_section, context("Tamer", "Entrantes"), ("other entrees", Method.SECTION, 0.4)),
])
def test_a_rule_decides_when_it_applies(rule, item, expected):
    assert outcome(rule(item)) == expected


@pytest.mark.parametrize(("rule", "item"), [
    (business_rules.strong_name_keyword, context("Pollo al curry")),
    (business_rules.non_food_word, context("Pizza Barbacoa")),
    (business_rules.specific_section, context("Coca-Cola", "Bebidas")),  # a generic section: rule 5b
    (business_rules.weak_name_keyword, context("Tamer")),
    (business_rules.rest_of_name, context("Tamer")),
    (business_rules.generic_section, context("Tamer", "Especialidades")),
    (business_rules.combo_description, context("Shia Chiao", description="3 dürüm + patatas")),  # not a combo
    (business_rules.weak_section, context("Tamer")),
])
def test_a_rule_stays_out_when_it_does_not_apply(rule, item):
    assert rule(item) is None


def test_a_generic_dish_keeps_the_generic_category_of_its_section():
    assert outcome(business_rules.generic_section(context("Postre del día", "Postres")))[0] == "generic sweets"


def test_the_first_rule_that_applies_decides():
    analysis = business_rules.ItemRuleAnalysis(KEYWORDS, TAXONOMY_CATEGORIES)

    # rule 1 (strong word in the name) before rule 3 (the section)
    assert outcome(analysis.decide(MenuItemText("Hamburguesa", "Pizzas"))) == ("burger", Method.NAME, 0.95)


def test_an_item_no_rule_decides_is_pending_with_its_weak_section_fallback():
    analysis = business_rules.ItemRuleAnalysis(KEYWORDS, TAXONOMY_CATEGORIES)

    pending = analysis.decide(MenuItemText("Shia Chiao", "Entrantes"))

    assert isinstance(pending, PendingItem)
    assert outcome(pending.fallback) == ("other entrees", Method.SECTION, 0.4)
