"""Each matching decision rule on its own, and their order."""

import pytest

from libs.matching.domain import Decision, Evidence
from libs.matching.matching_business_rules import (
    decide,
    decision_rules,
    distinctive_name_far_away,
    distinctive_name_nearby,
    generic_name_nearby,
    partly_similar_name_nearby,
    similar_name_at_same_address,
)


def evidence(name_score, *, specific=True, conflict=False, distance_m=20.0, same_address=False):
    return Evidence(name_score=name_score, name_is_specific=specific, name_conflict=conflict, distance_m=distance_m,
                    same_address=same_address, score=0.0)


@pytest.mark.parametrize(("rule", "applies", "does_not_apply", "decision"), [
    (distinctive_name_nearby, evidence(0.9), evidence(0.9, distance_m=300), Decision.ACCEPTED),
    (similar_name_at_same_address, evidence(0.6, specific=False, same_address=True),
     evidence(0.6, specific=False, conflict=True, same_address=True), Decision.ACCEPTED),
    (distinctive_name_far_away, evidence(0.9, distance_m=300), evidence(0.9, specific=False), Decision.REVIEW),
    (partly_similar_name_nearby, evidence(0.6), evidence(0.6, distance_m=300), Decision.REVIEW),
    (generic_name_nearby, evidence(0.9, specific=False), evidence(0.9, specific=False, distance_m=300),
     Decision.REVIEW),
])
def test_each_rule(rule, applies, does_not_apply, decision):
    assert rule(applies)[0] == decision
    assert rule(does_not_apply) is None


def test_the_first_rule_that_applies_decides():
    nearby_distinctive = evidence(0.9)  # also a "distinctive name, but far away" for its own rule

    assert distinctive_name_far_away(nearby_distinctive) is not None
    assert decide(nearby_distinctive) == (Decision.ACCEPTED, "distinctive name nearby")


def test_an_address_alone_never_decides():
    assert decide(evidence(0.2, same_address=True, distance_m=0)) == (None, "")


def test_the_rules_run_in_order():
    assert [rule.__name__ for rule in decision_rules()] == [
        "distinctive_name_nearby", "similar_name_at_same_address", "distinctive_name_far_away",
        "partly_similar_name_nearby", "generic_name_nearby"]
