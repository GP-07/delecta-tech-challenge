"""Matcher rules on small, made-up but realistic cases (coordinates in Barcelona)."""

import pytest

from libs.matching.domain import Decision, Evidence, Place
from libs.matching.matcher import Matcher
from libs.matching.matching_business_rules import decide

LAT, LON = 41.3900, 2.1600
METRE = 1 / 111_000  # ~1 metre in degrees of latitude


def place(id_, name, address, metres_north=0.0):
    return Place(id_, name, address, LAT + metres_north * METRE, LON)


# Many generic names so that word weights look like the real data.
FILLER = [place(f"f{position}", name, "Carrer de Mallorca, 1", 2000 + position) for position, name in enumerate(
    ["Restaurante Chino", "Bar Restaurante", "Pizzeria", "Doner Kebab", "Sushi Bar", "Cafeteria"] * 40)]


def matcher(*targets):
    return Matcher([*targets, *FILLER])


def test_same_distinctive_name_nearby_is_accepted():
    target = place("g1", "Tiflis Restaurant", "Carrer del Consell de Cent, 487, Eixample, 08013 Barcelona", 20)

    (match,) = matcher(target).match([place("j1", "Tiflis Restaurant", "Carrer del Consell de Cent, 487")])

    assert (match.target_id, match.decision) == ("g1", Decision.ACCEPTED)
    assert match.evidence.same_address


def _evidence(name, *, specific=True, conflict=False, distance=10.0, same_address=False):
    return Evidence(name_score=name, name_is_specific=specific, name_conflict=conflict, distance_m=distance,
                    same_address=same_address, score=0.0)


@pytest.mark.parametrize(("evidence", "decision"), [
    (_evidence(0.9), Decision.ACCEPTED),  # distinctive name nearby
    (_evidence(0.9, distance=250, same_address=True), Decision.ACCEPTED),  # same address in a large building
    (_evidence(0.6, same_address=True), Decision.ACCEPTED),  # "Atabalats Gastrobar" / "Atabalats Gastroburgers"
    (_evidence(0.6, specific=False, same_address=True), Decision.ACCEPTED),  # "Frankfurt Lys" / "Frankfurt"
    # "Restaurante Chino Dao" / "Restaurante Chino Sabroso": only common words shared, each its own brand
    (_evidence(0.6, specific=False, conflict=True, same_address=True), None),
    (_evidence(0.9, distance=300), Decision.REVIEW),  # distinctive name, but far away
    (_evidence(0.6), Decision.REVIEW),  # partly similar distinctive name nearby
    (_evidence(1.0, specific=False), Decision.REVIEW),  # "Doner Kebab y Pizzeria" twice, 11 m apart
    (_evidence(0.6, specific=False), None),  # partly similar generic name
    (_evidence(0.4, same_address=True), None),  # an address alone never decides
])
def test_decision_rules(evidence, decision):
    assert decide(evidence)[0] == decision


def test_generic_name_alone_is_never_accepted():
    target = place("g1", "Sushi", "Avinguda Meridiana, 300", 190)

    matches = matcher(target).match([place("j1", "Restaurante Aguila Sushi", "Avinguda Meridiana, 129")])

    assert matches == []


def test_two_venues_in_the_same_building_are_not_linked():
    """A shopping centre: same address, different brands sharing only the centre's name and common words."""
    target = place("g1", "Restaurante Chino Sabroso", "Carrer d'Arizala, 9, Sants-Montjuïc", 0)

    matches = matcher(target).match([place("j1", "Restaurante Chino Dao", "Carrer d'Arizala, 9")])

    assert all(match.decision != Decision.ACCEPTED for match in matches)


def test_a_distinctive_name_far_away_goes_to_review():
    target = place("g1", "Five Guys La Maquinista", "Centro Comercial La Maquinista, Carrer de Potosí, 2", 369)

    (match,) = matcher(target).match([place("j1", "Five Guys La Maquinista", "Carrer de Potosí")])

    assert match.decision == Decision.REVIEW


def test_nothing_beyond_the_search_radius():
    target = place("g1", "Tiflis Restaurant", "Carrer del Consell de Cent, 487", 1000)

    assert matcher(target).match([place("j1", "Tiflis Restaurant", "Carrer del Consell de Cent, 487")]) == []


def test_a_target_is_linked_to_one_source_only_the_best():
    target = place("g1", "Pans & Company Can Drago", "Avinguda de Rio de Janeiro, 42", 10)
    sources = [place("j1", "Café Pans Can Drago By P&C", "Avinguda de Rio de Janeiro, 42"),
               place("j2", "Pans & Company Can Drago", "Avinguda de Rio de Janeiro, 42")]

    (match,) = matcher(target).match(sources)

    assert (match.source_id, match.target_id) == ("j2", "g1")


def test_the_loser_falls_back_to_its_next_candidate():
    targets = [place("g1", "Goiko", "Via Laietana, 13", 5), place("g2", "Goiko", "Via Laietana, 15", 30)]
    sources = [place("j1", "Goiko Laietana", "Via Laietana, 13"), place("j2", "Goiko Barcelona", "Via Laietana, 15")]

    matches = matcher(*targets).match(sources)

    assert {(match.source_id, match.target_id) for match in matches} == {("j1", "g1"), ("j2", "g2")}


def test_taken_targets_and_rejected_pairs_are_skipped():
    targets = [place("g1", "Goiko", "Via Laietana, 13", 5), place("g2", "Goiko", "Via Laietana, 13", 8)]
    source = place("j1", "Goiko Laietana", "Via Laietana, 13")

    assert matcher(*targets).match([source], taken_targets=frozenset({"g1"}))[0].target_id == "g2"
    assert matcher(*targets).match([source], excluded_pairs=frozenset({("j1", "g1")}))[0].target_id == "g2"


@pytest.mark.parametrize("name", ["Goiko Laietana", "GOIKO laietana", "Goiko - Laietana"])
def test_the_result_is_deterministic(name):
    targets = [place("g1", "Goiko", "Via Laietana, 13", 5), place("g2", "Goiko", "Via Laietana, 13", 5)]

    assert matcher(*targets).match([place("j1", name, "Via Laietana, 13")])[0].target_id == "g1"
