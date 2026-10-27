import pytest

from libs.matching.names import NameScorer

# A tiny corpus: generic words appear in many names, brands in one.
CORPUS = (
    ["Restaurante Chino Sabroso", "Restaurante Chino Feliz", "Sushi Bar", "Sushi House", "Doner Kebab Pizzeria",
     "Ali Doner Kebab", "Bar Pizzeria", "Restaurante", "Bar", "Pizzeria"] * 20
    + ["Goiko", "Tiflis", "Atabalats Gastroburgers", "Mi Xiang", "Vibra Speakeasy", "Starbucks", "Lider de Istambul"]
)


@pytest.fixture(scope="module")
def scorer():
    return NameScorer(CORPUS)


def test_common_words_weigh_less_than_brands(scorer):
    assert scorer.weight("restaurante") < scorer.weight("sushi") < scorer.weight("goiko")


def test_same_name_with_accents_and_case(scorer):
    similarity = scorer.compare("Líder de Istambul", "Lider de Istambul")

    assert similarity.score == pytest.approx(1)
    assert similarity.specific


def test_branch_location_in_the_name_barely_counts(scorer):
    similarity = scorer.compare("Goiko Barcelona Laietana", "Goiko", location_words=frozenset({"laietana"}))

    assert similarity.score > 0.85
    assert similarity.specific


def test_sharing_only_a_common_word_is_not_specific(scorer):
    similarity = scorer.compare("Restaurante Aguila Sushi", "Sushi")

    assert not similarity.specific


def test_words_written_together_or_apart(scorer):
    assert scorer.compare("Mixiang", "Mi Xiang").score == pytest.approx(1)


def test_typos_get_partial_credit(scorer):
    assert 0.8 < scorer.compare("Tiflis Restaurante", "Tiflis Restaurant").score < 1


def test_each_name_with_its_own_distinctive_word_is_a_conflict(scorer):
    assert scorer.compare("Starbucks Room Mate", "Vibra Speakeasy Room Mate").conflict
    assert not scorer.compare("Goiko Barcelona", "Goiko").conflict


def test_empty_names(scorer):
    assert scorer.compare("", "Goiko").score == 0


def test_names_sharing_only_place_names_are_not_similar(scorer):
    """The shopping centre itself is listed in Google; a shop inside it is not the centre."""
    assert scorer.compare("Starbucks Diagonal Mar", "Diagonal Mar").score == 0
