"""Accuracy of the rules against real menu items labelled by hand (tests/fixtures/categorization).

labeled_items.json: 300 random items of venues linked to Google. They were read while the keywords were written,
so they measure how well the rules fit what they were built from (development set).
holdout_items.json: 200 other random items, labelled before looking at what the classifier said and never used to
change the rules: the honest measure (test set).

Each entry has the expected category name (None: not food nor drink). Labelling rules: the kind of dish before its
ingredients ("Ensalada de salmón": salads), a combo by its main dish, a curry by its meat, water and tonic as soft
drinks. The thresholds sit a little below the measured values, so a change that makes things worse fails here.
"""

import json
from pathlib import Path

import pytest

from libs.categorization.classifier import Classifier
from libs.categorization.constants import LOW_CONFIDENCE
from libs.categorization.domain import MenuItemText
from libs.categorization.taxonomy import read_taxonomy

FIXTURES = Path(__file__).parents[1] / "fixtures" / "categorization"
# Measured on 2026-10-26 (rules only): development 90.7% / 92.3% / 98.0%, holdout 79.0% / 81.5% / 94.5%.
MIN_ACCURACY = {
    "labeled_items": {"name": 0.88, "parent": 0.90, "family": 0.96},
    "holdout_items": {"name": 0.76, "parent": 0.78, "family": 0.92},
}
MIN_CONFIDENT_ACCURACY = 0.82  # holdout: 85.1% of the items with confidence >= LOW_CONFIDENCE are right


@pytest.fixture(scope="module")
def taxonomy():
    return read_taxonomy(FIXTURES / "food_categories.xlsx")


def evaluate(taxonomy, name):
    labeled = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    results = Classifier(taxonomy).classify([MenuItemText(entry["name"], entry["section"], entry["description"])
                                             for entry in labeled])
    return [(taxonomy[entry["category"]] if entry["category"] else None, result)
            for entry, result in zip(labeled, results, strict=True)]


def same_at_level(expected, got, level):
    """Both without a category, or the same at that level of the taxonomy (name, parent or family)."""
    if expected is None or got is None:
        return expected is got
    return getattr(expected, level) == getattr(got, level)


def accuracy(pairs, level):
    return sum(same_at_level(expected, result.category, level) for expected, result in pairs) / len(pairs)


@pytest.mark.parametrize("name", MIN_ACCURACY)
def test_accuracy_by_level(taxonomy, name):
    pairs = evaluate(taxonomy, name)

    measured = {level: accuracy(pairs, level) for level in ("name", "parent", "family")}

    assert all(measured[level] >= minimum for level, minimum in MIN_ACCURACY[name].items()), measured


def test_confident_classifications_are_mostly_right(taxonomy):
    confident = [(expected, result) for expected, result in evaluate(taxonomy, "holdout_items")
                 if result.confidence >= LOW_CONFIDENCE]

    assert accuracy(confident, "name") >= MIN_CONFIDENT_ACCURACY


def test_the_samples_cover_the_taxonomy(taxonomy):
    for name in MIN_ACCURACY:
        labeled = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        assert len({entry["category"] for entry in labeled}) >= 50
        assert {taxonomy[entry["category"]].family for entry in labeled if entry["category"]} == {"food", "drink"}
