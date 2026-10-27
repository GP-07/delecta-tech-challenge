"""Links the Just Eat venues crawled by a run to the Google venues of that run's file (StagedVenueMatch rows).

The matching only works on what the run's own crawl and Google load staged, and only after both succeeded: never on
data from another source or another run (a file loaded by hand, an older crawl...). The matching itself (which pairs
are the same venue) is the `matching` library; this module feeds it and stores what it returns.

People's decisions are read from the published links (VenueMatch) and respected: a venue whose link is CONFIRMED
(or waiting for a person because its Google place left the file) is not matched again, a Google place confirmed
for another venue is not proposed, and a REJECTED pair is never proposed again.
"""

import logging
from dataclasses import dataclass

from django.db import transaction

from apps.pipeline.constants import CRAWL_STEP, GOOGLE_LOAD_STEP
from apps.pipeline.models import PipelineRun
from apps.pipeline.steps import require_succeeded
from apps.venues.constants import MATCH_STATUS_OF_DECISION, PLACE_FIELDS
from apps.venues.models import ACTIVE_MATCH_STATUSES, MatchStatus, Source, StagedVenue, StagedVenueMatch, VenueMatch
from apps.venues.review_services import held_venues
from libs.matching.domain import Decision, Match, Place
from libs.matching.matcher import Matcher

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class MatchResult:
    venues: int  # Just Eat venues of the run with coordinates
    accepted: int
    review: int
    unmatched: int
    confirmed: int  # held by a person's decision, not matched again

    def as_metrics(self) -> dict:
        return dict(self.__dict__)


def match_run_venues(run: PipelineRun) -> MatchResult:
    return RunMatching(run).match()


def to_place(venue: StagedVenue) -> Place:
    """A staged venue as the matcher sees it; its id is the staged row's pk."""
    return Place(id=str(venue.pk), name=venue.name, address=venue.address,
                 latitude=venue.latitude, longitude=venue.longitude)


def to_staged_match(match: Match, run: PipelineRun) -> StagedVenueMatch:
    evidence = match.evidence
    return StagedVenueMatch(
        run=run, just_eat_id=int(match.source_id), google_id=int(match.target_id),
        status=MATCH_STATUS_OF_DECISION[match.decision], score=evidence.score, name_score=evidence.name_score,
        distance_m=evidence.distance_m, same_address=evidence.same_address, reason=match.reason,
        evidence=evidence.as_dict(),
    )


class RunMatching:
    """The staged venues of one run (with coordinates), and what people decided about them."""

    def __init__(self, run: PipelineRun) -> None:
        require_succeeded(run, CRAWL_STEP, GOOGLE_LOAD_STEP)
        self.run = run
        located = (StagedVenue.objects.filter(run=run, latitude__isnull=False, longitude__isnull=False)
                   .only(*PLACE_FIELDS))
        self.just_eat_venues = list(located.filter(source=Source.JUST_EAT))
        self.google_venues = list(located.filter(source=Source.GOOGLE))
        # External id -> staged pk (the id the matcher works with).
        self.just_eat_pk = {venue.external_id: str(venue.pk) for venue in self.just_eat_venues}
        self.google_pk = {venue.external_id: str(venue.pk) for venue in self.google_venues}

    def match(self) -> MatchResult:
        held = held_venues()
        sources = [to_place(venue) for venue in self.just_eat_venues if venue.external_id not in held]
        matcher = Matcher(to_place(venue) for venue in self.google_venues)
        matches = matcher.match(sources, taken_targets=self.taken_google_places(),
                                excluded_pairs=self.rejected_pairs())
        with transaction.atomic():
            StagedVenueMatch.objects.filter(run=self.run).delete()  # a step retried by the queue starts again
            StagedVenueMatch.objects.bulk_create([to_staged_match(match, self.run) for match in matches])

        accepted = sum(1 for match in matches if match.decision == Decision.ACCEPTED)
        result = MatchResult(venues=len(self.just_eat_venues), accepted=accepted, review=len(matches) - accepted,
                             unmatched=len(sources) - len(matches), confirmed=len(set(self.just_eat_pk) & held))
        logger.info("run=%s matching: %s", self.run.pk, result)
        return result

    def taken_google_places(self) -> frozenset[str]:
        """Google places of the run linked to another venue: confirmed by a person, or linked automatically to a
        venue this run did not crawl. The automatic links of the run's own venues are computed again."""
        taken = set()
        for just_eat_id, google_id, status in VenueMatch.objects.filter(status__in=ACTIVE_MATCH_STATUSES).values_list(
                "just_eat__external_id", "google__external_id", "status"):
            if google_id in self.google_pk and (status == MatchStatus.CONFIRMED or just_eat_id not in self.just_eat_pk):
                taken.add(self.google_pk[google_id])
        return frozenset(taken)

    def rejected_pairs(self) -> frozenset[tuple[str, str]]:
        """(Just Eat, Google) staged pks of the pairs a person rejected."""
        rejected = VenueMatch.objects.filter(status=MatchStatus.REJECTED).values_list(
            "just_eat__external_id", "google__external_id")
        return frozenset((self.just_eat_pk[just_eat_id], self.google_pk[google_id])
                         for just_eat_id, google_id in rejected
                         if just_eat_id in self.just_eat_pk and google_id in self.google_pk)
