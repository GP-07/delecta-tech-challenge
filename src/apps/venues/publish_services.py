"""Publishes the venues and links a run staged (part of publish_run, inside its transaction).

    Google venues   replaced by the run's file: created, updated, and removed when no longer in it. A Google venue
                    that left the file but has a link a person confirmed is kept, and the link goes back to REVIEW
                    (google_missing) until a person decides again; if the place comes back, it is CONFIRMED again.
    Just Eat venues the run's are created or updated (last_run = run); venues it did not crawl are kept as they are.
    Links           the automatic links (ACCEPTED, REVIEW) of the run's venues are replaced by the run's. A decision a
                    person took while the run was going (confirm, reject) wins over what the run proposed.
"""

from dataclasses import dataclass

from apps.pipeline.models import PipelineRun
from apps.venues.constants import (
    AUTOMATIC_MATCH_STATUSES,
    GOOGLE_MISSING_REASON,
    MATCH_EVIDENCE_FIELDS,
    PUBLISH_CHUNK_SIZE,
    VENUE_FIELDS,
)
from apps.venues.models import (
    ACTIVE_MATCH_STATUSES,
    MatchStatus,
    Source,
    StagedVenue,
    StagedVenueMatch,
    Venue,
    VenueMatch,
)


@dataclass(frozen=True)
class VenuesPublished:
    google: int
    google_removed: int
    google_missing: int  # links a person confirmed whose Google place left the file: back to review
    just_eat: int
    matches: int
    matches_skipped: int  # proposed by the run, but a person decided otherwise meanwhile


def publish_venues(run: PipelineRun) -> VenuesPublished:
    return VenuePublisher(run).publish()


class VenuePublisher:
    """Copies one run's staged venues and links to the published tables, in this order: Google venues, the Google
    venues no longer in the file, Just Eat venues, links."""

    def __init__(self, run: PipelineRun) -> None:
        self.run = run
        self.staged_google_ids = StagedVenue.objects.filter(run=run, source=Source.GOOGLE).values("external_id")
        self.staged_just_eat_ids = StagedVenue.objects.filter(run=run, source=Source.JUST_EAT).values("external_id")

    def publish(self) -> VenuesPublished:
        google = self._copy(Source.GOOGLE)
        google_removed, google_missing = self._remove_missing_google()
        just_eat = self._copy(Source.JUST_EAT)
        matches, skipped = self._publish_matches()
        return VenuesPublished(google=google, google_removed=google_removed, google_missing=google_missing,
                               just_eat=just_eat, matches=matches, matches_skipped=skipped)

    def _copy(self, source: str) -> int:
        """Upserts the staged venues of a source, a chunk at a time (Just Eat rows carry their menus)."""
        staged = StagedVenue.objects.filter(run=self.run, source=source).order_by("pk")
        staged_pks = list(staged.values_list("pk", flat=True))
        for start in range(0, len(staged_pks), PUBLISH_CHUNK_SIZE):
            rows = [Venue(source=source, external_id=venue.external_id, last_run=self.run,
                          **{field: getattr(venue, field) for field in VENUE_FIELDS})
                    for venue in staged.filter(pk__in=staged_pks[start:start + PUBLISH_CHUNK_SIZE])]
            Venue.objects.bulk_create(rows, update_conflicts=True, unique_fields=["source", "external_id"],
                                      update_fields=[*VENUE_FIELDS, "last_run", "updated_at"])
        return len(staged_pks)

    def _remove_missing_google(self) -> tuple[int, int]:
        """Returns (Google venues removed, confirmed links sent back to review because their place left)."""
        missing = Venue.objects.filter(source=Source.GOOGLE).exclude(external_id__in=self.staged_google_ids)
        back_in_file = VenueMatch.objects.filter(google_missing=True).exclude(google__in=missing)
        back_in_file.filter(status=MatchStatus.REVIEW).update(status=MatchStatus.CONFIRMED, google_missing=False)
        back_in_file.update(google_missing=False)
        newly_missing = VenueMatch.objects.filter(google__in=missing, status=MatchStatus.CONFIRMED,
                                                  google_missing=False)
        back_to_review = newly_missing.update(status=MatchStatus.REVIEW, google_missing=True,
                                              reason=GOOGLE_MISSING_REASON)
        waiting = VenueMatch.objects.filter(google_missing=True,
                                            status__in=[MatchStatus.CONFIRMED, MatchStatus.REVIEW])
        _, deleted = missing.exclude(pk__in=waiting.values("google")).delete()  # and, in cascade, their other links
        return deleted.get(Venue._meta.label, 0), back_to_review

    def _publish_matches(self) -> tuple[int, int]:
        """Returns (links published, links skipped because a person decided otherwise while the run was going)."""
        run_venues = Venue.objects.filter(source=Source.JUST_EAT, external_id__in=self.staged_just_eat_ids)
        VenueMatch.objects.filter(just_eat__in=run_venues, status__in=AUTOMATIC_MATCH_STATUSES,
                                  google_missing=False).delete()
        just_eat_pk = dict(run_venues.values_list("external_id", "pk"))
        google_pk = dict(Venue.objects.filter(source=Source.GOOGLE).values_list("external_id", "pk"))
        active = VenueMatch.objects.filter(status__in=ACTIVE_MATCH_STATUSES)
        linked_just_eat = set(active.values_list("just_eat_id", flat=True))
        linked_google = set(active.values_list("google_id", flat=True))
        rejected = set(VenueMatch.objects.filter(status=MatchStatus.REJECTED).values_list("just_eat_id", "google_id"))

        rows, skipped = [], 0
        for match in StagedVenueMatch.objects.filter(run=self.run).select_related("just_eat", "google").defer(
                "just_eat__menus", "just_eat__opening_times", "just_eat__details", "google__details"):
            just_eat, google = just_eat_pk[match.just_eat.external_id], google_pk[match.google.external_id]
            if just_eat in linked_just_eat or google in linked_google or (just_eat, google) in rejected:
                skipped += 1  # a person confirmed, rejected or linked one of them while the run was going
                continue
            linked_just_eat.add(just_eat)
            linked_google.add(google)
            rows.append(VenueMatch(just_eat_id=just_eat, google_id=google, status=match.status, run=self.run,
                                   **{field: getattr(match, field) for field in MATCH_EVIDENCE_FIELDS}))
        VenueMatch.objects.bulk_create(rows)
        return len(rows), skipped
