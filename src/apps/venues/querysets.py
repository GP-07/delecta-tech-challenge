"""Querysets of the published venues, to ask for the venues of a run and of a match group directly:

    Venue.objects.crawled_by(run).in_match_group(MatchGroup.REVIEW).without_large_fields()
    Venue.objects.crawled_by(run).linked()
"""

from django.apps import apps
from django.db import models
from django.db.models import Exists, OuterRef

from apps.venues.choices import ACTIVE_MATCH_STATUSES, LINKED_MATCH_STATUSES, MatchGroup, MatchStatus, Source

LARGE_FIELDS = ("menus", "opening_times", "details")  # up to MBs per venue, and never shown in lists


def has_match(statuses: list[str]) -> Exists:
    """The venue (the outer query's row) has a link to Google in one of these statuses."""
    venue_match = apps.get_model("venues", "VenueMatch")
    return Exists(venue_match.objects.filter(just_eat=OuterRef("pk"), status__in=statuses))


def match_group_condition(group: str):
    """The condition of a match group, usable in filter() and in Count(filter=...). The groups do not overlap: a
    venue has at most one active link, and a rejected one counts only without an active link."""
    return {
        MatchGroup.ACCEPTED: has_match([MatchStatus.ACCEPTED]),
        MatchGroup.CONFIRMED: has_match([MatchStatus.CONFIRMED]),
        MatchGroup.REVIEW: has_match([MatchStatus.REVIEW]),
        MatchGroup.REJECTED: has_match([MatchStatus.REJECTED]) & ~has_match(ACTIVE_MATCH_STATUSES),
        MatchGroup.UNMATCHED: ~has_match([*ACTIVE_MATCH_STATUSES, MatchStatus.REJECTED]),
    }[group]


class VenueQuerySet(models.QuerySet):
    def just_eat(self) -> "VenueQuerySet":
        return self.filter(source=Source.JUST_EAT)

    def crawled_by(self, run) -> "VenueQuerySet":
        """The Just Eat venues the run crawled (and published)."""
        return self.just_eat().filter(last_run=run)

    def in_match_group(self, group: str) -> "VenueQuerySet":
        return self.filter(match_group_condition(group))

    def linked(self) -> "VenueQuerySet":
        """Matched: accepted automatically or confirmed by a person."""
        return self.filter(has_match(LINKED_MATCH_STATUSES))

    def without_large_fields(self) -> "VenueQuerySet":
        return self.defer(*LARGE_FIELDS)
