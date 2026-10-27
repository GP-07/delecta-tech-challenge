import numpy as np
import pytest

from libs.categorization.classifier import Classifier
from libs.categorization.domain import MenuItemText, Method
from libs.categorization.taxonomy import read_taxonomy
from tests.categorization.test_taxonomy import TAXONOMY


class WordEmbedder:
    """Fake embedder: one dimension per word, so texts sharing words are similar."""

    def __init__(self):
        self.vocabulary: dict[str, int] = {}
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        rows = []
        for text in texts:
            vector = np.zeros(256, dtype=np.float32)
            for word in text.lower().replace("|", " ").split():
                vector[self.vocabulary.setdefault(word, len(self.vocabulary) % 256)] += 1
            rows.append(vector / (np.linalg.norm(vector) or 1))
        return np.array(rows)


@pytest.fixture(scope="module")
def taxonomy():
    return read_taxonomy(TAXONOMY)


@pytest.fixture(scope="module")
def classifier(taxonomy):
    return Classifier(taxonomy)


def classify(classifier, name, section="", description=""):
    return classifier.classify([MenuItemText(name, section, description)])[0]


@pytest.mark.parametrize(("name", "section", "description", "category", "method", "confidence"), [
    # 1. a strong keyword in the head of the name decides
    ("Ensalada de salmón", "Entrantes", "", "salads", Method.NAME, 0.95),
    ("Pollo Asado + Coca-Cola", "", "", "chicken", Method.NAME, 0.75),  # head "pollo asado"; the drink is a side
    ("Pizza 4 Quesos", "Ofertas", "", "pizza", Method.NAME, 0.95),
    # 3. a strong section beats the ingredients of the name
    ("Carbonara", "Pizzas Medianas", "", "pizza", Method.SECTION, 0.85),
    ("Bacon Queso", "Hamburguesas", "", "burger", Method.SECTION, 0.85),
    # a precise category of the section beats a generic one
    ("Espelt Mareny Blanco", "Vinos Blancos", "", "blancos", Method.NAME, 0.95),
    ("Mushroom Rice", "Platos Biryani", "", "other rice", Method.SECTION, 0.95),
    # 4. an ingredient in the head of the name
    ("Pollo al curry", "Platos", "", "chicken", Method.NAME, 0.75),
    # 5. the rest of the name, before a generic section
    ("Eristoff, 50ml - Vodka", "Bebidas Alcohólicas", "", "other espirituosas", Method.NAME, 0.65),
    # 6. a combo is what its description says
    ("Menú 3", "Menús", "3 dürüm + patatas + Coca-Cola 2L", "kebab", Method.DESCRIPTION, 0.6),
])
def test_rules_in_order(classifier, name, section, description, category, method, confidence):
    result = classify(classifier, name, section, description)

    assert (result.category.name, result.method, result.confidence) == (category, method, confidence)


def test_a_concrete_dish_of_a_generic_section_is_other_and_a_generic_one_stays_generic(classifier):
    assert classify(classifier, "Tamer", "Postres").category.name == "other sweets"
    assert classify(classifier, "Postre del día", "Postres").category.name == "generic sweets"


def test_course_sections_are_the_last_resort(classifier):
    result = classify(classifier, "Pkhali Mix", "Entrantes/Starters")

    assert (result.category.name, result.method, result.confidence) == ("other entrees", Method.SECTION, 0.4)


def test_things_that_are_not_food_get_no_category(classifier):
    result = classify(classifier, "Palillos (1 juego)", "Menús Diarios")

    assert (result.category, result.method) == (None, Method.NON_FOOD)


def test_without_any_clue_the_item_has_no_category(classifier):
    result = classify(classifier, "Khachapuri Adjaruli", "Especialidades")

    assert (result.category, result.method, result.confidence) == (None, Method.UNKNOWN, 0)


def test_combos_are_flagged(classifier):
    assert classify(classifier, "Menú 5", "Menús", "Medio pollo, patatas y bebida").is_combo
    assert not classify(classifier, "Pollo asado", "Platos").is_combo


def test_embeddings_decide_what_the_rules_cannot_with_the_items_the_rules_did(taxonomy):
    embedder = WordEmbedder()
    classifier = Classifier(taxonomy, embedder, min_similarity=0.2)
    items = [MenuItemText("Khachapuri de queso", "Pizzas georgianas"),  # its section says it is a pizza
             MenuItemText("Khachapuri adjaruli", "Especialidades")]  # no rule says anything

    reference, guess = classifier.classify(items)

    assert reference.category.name == "pizza"
    assert (guess.category.name, guess.method) == ("pizza", Method.EMBEDDING)
    assert guess.evidence.startswith("Khachapuri de queso")
    assert 0 < guess.confidence <= 0.5  # an embedding guess is always low confidence


def test_dissimilar_items_keep_their_section_or_stay_unknown(taxonomy):
    classifier = Classifier(taxonomy, WordEmbedder(), min_similarity=0.9)
    items = [MenuItemText("Pizza Margarita", "Pizzas"), MenuItemText("Bazhe", "Entrantes"),
             MenuItemText("Shoti", "Especialidades")]

    _, bazhe, shoti = classifier.classify(items)

    assert (bazhe.category.name, bazhe.method) == ("other entrees", Method.SECTION)
    assert (shoti.category, shoti.method) == (None, Method.UNKNOWN)


def test_references_from_earlier_runs_are_used_and_the_embedder_is_not_called_when_rules_decide(taxonomy):
    embedder = WordEmbedder()
    classifier = Classifier(taxonomy, embedder, min_similarity=0.2)

    classifier.classify([MenuItemText("Pizza Margarita", "Pizzas")])
    assert embedder.calls == 0

    result = classifier.classify([MenuItemText("Lobiani casero", "Especialidades")],
                                 references=[(MenuItemText("Lobiani de alubias", "Panes"), "bread")])
    assert (result[0].category.name, result[0].method) == ("bread", Method.EMBEDDING)
