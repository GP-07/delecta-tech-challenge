import pytest

from libs.categorization import constants
from libs.categorization.domain import Strength
from libs.categorization.item_context import head_end
from libs.categorization.keywords import KeywordRules
from libs.categorization.taxonomy import read_taxonomy
from libs.categorization.text_helpers import normalize
from tests.categorization.test_taxonomy import TAXONOMY

NAMES = {category.name for category in read_taxonomy(TAXONOMY).categories}


@pytest.fixture(scope="module")
def rules():
    return KeywordRules(NAMES)


def words(text):
    return normalize(text).split()


def found(rules, text):
    return [(hit.category, hit.strength) for hit in rules.hits(words(text))]


def test_normalize_drops_accents_and_keeps_the_connectors():
    assert normalize("Pollo Asado + Coca-Cola, 33cl") == "pollo asado + coca cola , 33cl"
    assert normalize("Dürüm Kebab & Patatas") == "durum kebab and patatas"


@pytest.mark.parametrize(("name", "head"), [
    ("Pollo asado con patatas", "pollo asado"),
    ("Pizza + Coca-Cola", "pizza"),
    ("Eristoff, 50ml - Vodka", "eristoff"),
    ("Salmó i alvocat", "salmo"),
    ("Croquetas de jamón", "croquetas de jamon"),
])
def test_the_head_of_a_name_ends_at_its_first_connector(name, head):
    assert words(name)[:head_end(words(name))] == head.split()


def test_strong_and_weak_keywords_are_found_in_order(rules):
    assert found(rules, "Hamburguesa de pollo") == [("burger", Strength.STRONG), ("chicken", Strength.WEAK)]


def test_plurals_and_the_longest_keyword_match(rules):
    assert found(rules, "Pizzas familiares") == [("pizza", Strength.STRONG)]
    assert found(rules, "Patatas bravas") == [("tapas", Strength.STRONG)]  # not "patatas" (fries)
    assert found(rules, "Tortilla chips") == [("nachos", Strength.STRONG)]  # not "tortilla" (omelette)


def test_an_anchored_keyword_only_counts_at_the_start(rules):
    assert found(rules, "Salsa barbacoa") == [("sauces", Strength.STRONG)]
    assert found(rules, "Pollo en salsa") == [("chicken", Strength.WEAK)]


def test_non_food_combo_and_generic_words(rules):
    assert rules.is_non_food(words("Palillos (1 juego)"))
    assert rules.is_combo(words("Menú 3 dürüm")) and rules.is_combo(words("Pizza + bebida"))
    assert rules.is_generic(words("Postre del día")) and not rules.is_generic(words("Tarta de queso"))


def test_rules_refuse_categories_missing_from_the_taxonomy():
    with pytest.raises(ValueError, match="missing from the taxonomy"):
        KeywordRules(NAMES - {"pizza"})


def test_a_keyword_cannot_belong_to_two_categories(monkeypatch):
    monkeypatch.setitem(constants.WEAK_KEYWORDS, "salmon", (*constants.WEAK_KEYWORDS["salmon"], "pizza"))

    with pytest.raises(ValueError, match="two categories"):
        KeywordRules(NAMES)


def test_a_keyword_written_as_in_the_text_wins_over_one_read_as_its_plural(rules):
    # "patatas asadas" (fries) and "patata asada" (other vegetables) both match "Patatas asadas" with two words.
    assert found(rules, "Patatas asadas, ración")[0] == ("fries", Strength.STRONG)
