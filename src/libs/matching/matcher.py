"""Links every source place (Just Eat) to at most one target place (Google), and every target to at most one source.

    matcher = Matcher(google_places)
    matches = matcher.match(just_eat_places)        # [Match(source_id, target_id, decision, reason, evidence)]

For each source place:
    1. candidates: the target places within SEARCH_RADIUS_M (400 m), found with the grid of geo.py
    2. evidence:   for each candidate, how similar the names are (names.py: weighted by how distinctive the words
                   are), how far apart they are, and whether they share street and number (address.py)
    3. decision:   matching_business_rules.decide: ACCEPTED, REVIEW, or not a candidate

Then the candidate pairs of all sources are assigned greedily, surest first (matching_business_rules.ranking_key):
a pair is taken unless its source or its target was already taken by a surer pair. So when two Just Eat venues
claim the same Google place, the one with the better evidence gets it and the other falls back to its next
candidate, if any. Greedy is enough here: conflicts are rare (a few per thousand venues) and the surest pair is
almost always the right one.

A source without an accepted or review candidate stays unmatched: most of them simply are not in the target data
(supermarkets, virtual brands, venues outside the area it covers).
"""

from collections.abc import Iterable, Sequence
from operator import attrgetter

from libs.matching.address import Address
from libs.matching.constants import SEARCH_RADIUS_M
from libs.matching.domain import Evidence, Match, Place
from libs.matching.geo import GridIndex
from libs.matching.matching_business_rules import decide, overall_score, ranking_key
from libs.matching.names import NameScorer
from libs.matching.normalization_business_rules import tokens


class Matcher:
    def __init__(self, targets: Iterable[Place]) -> None:
        self._targets = list(targets)
        self._index = GridIndex(self._targets)
        self._names = NameScorer(target.name for target in self._targets)

    def match(self, sources: Iterable[Place], *, taken_targets: frozenset[str] = frozenset(),
              excluded_pairs: frozenset[tuple[str, str]] = frozenset()) -> list[Match]:
        """`taken_targets`: already linked elsewhere (e.g. confirmed by a person); `excluded_pairs`:
        (source_id, target_id) pairs a person rejected."""
        pairs = [
            match
            for source in sources
            for match in self.candidates(source)
            if match.target_id not in taken_targets and (match.source_id, match.target_id) not in excluded_pairs
        ]
        pairs.sort(key=ranking_key)
        assigned: dict[str, Match] = {}
        used_targets: set[str] = set()
        for match in pairs:
            if match.source_id not in assigned and match.target_id not in used_targets:
                assigned[match.source_id] = match
                used_targets.add(match.target_id)
        return sorted(assigned.values(), key=attrgetter("source_id"))

    def candidates(self, source: Place) -> Sequence[Match]:
        """Every target near `source` that the rules accept or send to review, surest first."""
        source_address = Address.parse(source.address)
        found = []
        for target, distance in self._index.near(source, SEARCH_RADIUS_M):
            evidence = self._evidence(source, target, distance, source_address)
            decision, reason = decide(evidence)
            if decision is not None:
                found.append(Match(source.id, target.id, decision, reason, evidence))
        return sorted(found, key=ranking_key)

    def _evidence(self, source: Place, target: Place, distance: float, source_address: Address) -> Evidence:
        # Words of either address weigh little in the names: "Goiko Pau Claris" at "Carrer de Pau Claris, 77".
        location_words = frozenset(tokens(source.address)) | frozenset(tokens(target.address))
        name = self._names.compare(source.name, target.name, location_words=location_words)
        same_address = source_address.same_as(Address.parse(target.address))
        return Evidence(name_score=name.score, name_is_specific=name.specific, name_conflict=name.conflict,
                        distance_m=distance, same_address=same_address,
                        score=overall_score(name.score, distance, same_address))
