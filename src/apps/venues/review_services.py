"""Decisions of people on the links between Just Eat venues and Google places (from the admin).

A decision is final: no run changes a CONFIRMED or REJECTED link again (see matching_services and publish_services).
"""

from django.db.models import Q
from django.utils import timezone

from apps.venues.models import MatchStatus, VenueMatch


def confirm(match: VenueMatch, user) -> None:
    """A person says this pair is right: it is kept as CONFIRMED and no run changes it again."""
    _review(match, MatchStatus.CONFIRMED, user)


def reject(match: VenueMatch, user) -> None:
    """A person says this pair is wrong: it is kept as REJECTED so it is never proposed again."""
    _review(match, MatchStatus.REJECTED, user)


def held_venues() -> set[str]:
    """External ids of the Just Eat venues whose published link waits on, or was decided by, a person."""
    return set(VenueMatch.objects.filter(Q(status=MatchStatus.CONFIRMED) | Q(google_missing=True))
               .values_list("just_eat__external_id", flat=True))


def _review(match: VenueMatch, status: MatchStatus, user) -> None:
    match.status, match.reviewed_by, match.reviewed_at = status, user, timezone.now()
    match.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
