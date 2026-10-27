from django.db import models


class Source(models.TextChoices):
    JUST_EAT = "just_eat", "Just Eat"
    GOOGLE = "google", "Google"


class MatchStatus(models.TextChoices):
    ACCEPTED = "ACCEPTED", "Aceptado automáticamente"
    REVIEW = "REVIEW", "A revisar"
    CONFIRMED = "CONFIRMED", "Confirmado"
    REJECTED = "REJECTED", "Rechazado"


class MatchGroup(models.TextChoices):
    """Where a crawled Just Eat venue stands with Google: every venue is in exactly one group."""

    ACCEPTED = "accepted", "Aceptados automáticamente"
    CONFIRMED = "confirmed", "Confirmados por una persona"
    REVIEW = "review", "A revisar"
    REJECTED = "rejected", "Rechazados"
    UNMATCHED = "unmatched", "Sin match"


ACTIVE_MATCH_STATUSES = [MatchStatus.ACCEPTED, MatchStatus.REVIEW, MatchStatus.CONFIRMED]  # at most one per venue
LINKED_MATCH_STATUSES = [MatchStatus.ACCEPTED, MatchStatus.CONFIRMED]  # a "matched" venue: its items are categorized
