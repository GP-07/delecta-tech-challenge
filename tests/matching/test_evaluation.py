"""Accuracy against a labelled sample of 200 real Just Eat venues (tests/fixtures/matching).

labeled_pairs.json: for each Just Eat venue, the Google place(s) it is, or none. Labelled by hand from the
nearby Google places; `ambiguous` cases are left out of the metrics and `no_match_also_ok` marks venues that
compete with another Just Eat venue for the same Google place (only one of them can get it).
The thresholds guard the precision of what is linked automatically above all.
"""

import gzip
import json
from pathlib import Path

import pytest

from libs.matching.domain import Decision, Place
from libs.matching.matcher import Matcher

FIXTURES = Path(__file__).parents[1] / "fixtures" / "matching"
MIN_PRECISION = 0.97  # of the automatic links
MIN_RECALL_ACCEPTED = 0.85
MIN_RECALL_WITH_REVIEW = 0.90


@pytest.fixture(scope="module")
def outcome():
    google = [Place(*row) for row in json.loads(gzip.decompress((FIXTURES / "google_places.json.gz").read_bytes()))]
    just_eat = [Place(*row) for row in json.loads((FIXTURES / "just_eat_places.json").read_text(encoding="utf-8"))]
    labels = [label for label in json.loads((FIXTURES / "labeled_pairs.json").read_text(encoding="utf-8"))
              if "ambiguous" not in label]
    matches = {match.source_id: match for match in Matcher(google).match(just_eat)}
    return labels, matches


def _counts(outcome):
    labels, matches = outcome
    right = wrong = right_in_review = 0
    for label in labels:
        match = matches.get(label["just_eat_id"])
        if match is None:
            continue
        correct = match.target_id in label["google_ids"]
        if match.decision == Decision.ACCEPTED:
            right, wrong = right + correct, wrong + (not correct)
        else:
            right_in_review += correct
    positives = sum(1 for label in labels if label["google_ids"])
    return right, wrong, right_in_review, positives


def test_the_sample_covers_matches_and_non_matches(outcome):
    labels, _ = outcome
    assert sum(1 for label in labels if label["google_ids"]) >= 90
    assert sum(1 for label in labels if not label["google_ids"]) >= 90


def test_automatic_links_are_precise(outcome):
    right, wrong, _, _ = _counts(outcome)

    assert right / (right + wrong) >= MIN_PRECISION


def test_most_venues_are_linked(outcome):
    right, _, right_in_review, positives = _counts(outcome)

    assert right / positives >= MIN_RECALL_ACCEPTED
    assert (right + right_in_review) / positives >= MIN_RECALL_WITH_REVIEW
