from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.venues.choices import ACTIVE_MATCH_STATUSES, LINKED_MATCH_STATUSES, MatchGroup, MatchStatus, Source
from apps.venues.querysets import VenueQuerySet

__all__ = ["ACTIVE_MATCH_STATUSES", "LINKED_MATCH_STATUSES", "MatchGroup", "MatchStatus", "Source", "StagedVenue",
           "StagedVenueMatch", "Venue", "VenueMatch"]


class VenueData(models.Model):
    """The fields of a venue, shared by the published table (Venue) and the run's working table (StagedVenue)."""

    source = models.CharField(max_length=16, choices=Source.choices)
    external_id = models.CharField(
        max_length=255, help_text="Id del venue en la fuente (Just Eat: restaurant id; Google: place id).")
    name = models.CharField(max_length=255)
    brand = models.CharField(max_length=255, blank=True, null=True)
    unique_name = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=128, blank=True)
    address = models.CharField(max_length=255, blank=True)
    postal_code = models.CharField(max_length=16, blank=True, db_index=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    rating_count = models.PositiveIntegerField(null=True, blank=True)
    star_rating = models.FloatField(null=True, blank=True)
    cuisines = ArrayField(models.CharField(max_length=64), default=list, blank=True)
    store_front_type = models.CharField(max_length=32, blank=True)
    is_test = models.BooleanField(default=False)
    url = models.URLField(max_length=500, blank=True)
    logo_url = models.URLField(max_length=500, blank=True, null=True)
    description = models.TextField(blank=True)
    opening_times = models.JSONField(default=list, blank=True)
    menus = models.JSONField(default=dict, blank=True)  # as in just_eat_venues.json: {menu hash: menu}
    details = models.JSONField(default=dict, blank=True, help_text="Datos propios de la fuente (Google: web, tags…).")

    class Meta:
        abstract = True


class Venue(VenueData):
    """The published state of a venue of a source: what the admin and the dashboard show.

    Only the publish_run step writes it, from the StagedVenue rows of a run whose other steps all succeeded, in a
    single transaction: a run that fails halfway never leaves half of its data here. Keyed by
    (source, external_id); `last_run` says which run published this version. Just Eat venues come from the crawl
    (the full history stays in the JSON file of each run); Google venues come from the Google venues file of
    `last_run` (its path and SHA-256 are recorded in the run).
    """

    last_run = models.ForeignKey("pipeline.PipelineRun", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+", help_text="Corrida que escribió esta versión (vacío: manual).")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = VenueQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["source", "external_id"], name="unique_venue_per_source"),
        ]
        indexes = [models.Index(fields=["name"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_source_display()} {self.external_id})"


class StagedVenue(VenueData):
    """A venue as a run's steps wrote it, before publish_run copies it to Venue. Deleted when the run is published;
    kept for a while after a failure, for diagnosis (PIPELINE_STAGING_RETENTION_DAYS)."""

    run = models.ForeignKey("pipeline.PipelineRun", on_delete=models.CASCADE, related_name="+")

    class Meta:
        verbose_name = "venue de una corrida"
        constraints = [
            models.UniqueConstraint(fields=["run", "source", "external_id"], name="unique_staged_venue_per_run"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_source_display()} {self.external_id}, run {self.run_id})"


class MatchData(models.Model):
    """The evidence of a match, shared by VenueMatch and StagedVenueMatch."""

    score = models.FloatField()
    name_score = models.FloatField()
    distance_m = models.FloatField()
    same_address = models.BooleanField()
    reason = models.CharField(max_length=128)
    evidence = models.JSONField(default=dict)

    class Meta:
        abstract = True


class VenueMatch(MatchData):
    """A Just Eat venue linked to the Google venue it is (published; see Venue).

    ACCEPTED and REVIEW are proposed by the match_venues step and replaced by every published run. CONFIRMED and
    REJECTED are a person's decision and are never overwritten: a confirmed pair stays linked, a rejected pair is
    never proposed again. A venue has at most one active (accepted, review or confirmed) match on each side.

    `google_missing`: the Google place is no longer in the Google venues file. A confirmed match then goes back to
    REVIEW (and its Google venue is kept) until a person decides again; confirmed again, it stays.
    """

    just_eat = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name="google_matches",
                                 limit_choices_to={"source": Source.JUST_EAT})
    google = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name="just_eat_matches",
                               limit_choices_to={"source": Source.GOOGLE})
    status = models.CharField(max_length=16, choices=MatchStatus.choices, db_index=True)
    google_missing = models.BooleanField(default=False, help_text="La ficha de Google ya no está en el archivo.")
    run = models.ForeignKey("pipeline.PipelineRun", null=True, blank=True, on_delete=models.SET_NULL,
                            related_name="+", help_text="Corrida que lo propuso.")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-score"]
        verbose_name = "vínculo Just Eat - Google"
        verbose_name_plural = "vínculos Just Eat - Google"
        constraints = [
            models.UniqueConstraint(fields=["just_eat", "google"], name="unique_match_pair"),
            models.UniqueConstraint(fields=["just_eat"], condition=models.Q(status__in=ACTIVE_MATCH_STATUSES),
                                    name="one_active_match_per_just_eat_venue"),
            models.UniqueConstraint(fields=["google"], condition=models.Q(status__in=ACTIVE_MATCH_STATUSES),
                                    name="one_active_match_per_google_venue"),
        ]

    def __str__(self) -> str:
        return f"{self.just_eat.name} → {self.google.name} ({self.get_status_display()})"


class StagedVenueMatch(MatchData):
    """A link proposed by a run's match_venues step (ACCEPTED or REVIEW), before publish_run copies it."""

    run = models.ForeignKey("pipeline.PipelineRun", on_delete=models.CASCADE, related_name="+")
    just_eat = models.ForeignKey(StagedVenue, on_delete=models.CASCADE, related_name="google_matches")
    google = models.ForeignKey(StagedVenue, on_delete=models.CASCADE, related_name="just_eat_matches")
    status = models.CharField(max_length=16, choices=MatchStatus.choices)

    class Meta:
        verbose_name = "vínculo de una corrida"
        constraints = [
            models.UniqueConstraint(fields=["just_eat"], name="one_staged_match_per_just_eat_venue"),
            models.UniqueConstraint(fields=["google"], name="one_staged_match_per_google_venue"),
        ]
