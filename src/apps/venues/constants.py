"""Fixed values of the venues app: batch sizes, the fields copied around, and the texts it writes."""

import re

from apps.venues.models import MatchStatus, StagedVenue
from libs.matching.domain import Decision

PUBLISH_CHUNK_SIZE = 200  # venues per upsert when publishing (Just Eat rows carry their menus)
JUST_EAT_CHUNK_SIZE = 200  # Just Eat venues per INSERT; their menus make each row large (~70 KB on average)
GOOGLE_CHUNK_SIZE = 1000  # Google venues per INSERT
POSTAL_CODE = re.compile(r"\b(\d{5})\b")  # in a Google raw address
# Fields of a Google place kept as they are in `Venue.details`: useful for the dashboard, not needed as columns.
GOOGLE_DETAIL_FIELDS = (
    "website", "telephone", "euroScale", "timetable", "menuUrl", "temporalClosedAt", "tagsRestaurantGoogle",
    "googleTypeTags", "ownerClaimed", "reservationUrlsJson",
)

# Fields of a staged venue the matcher needs (never its menus).
PLACE_FIELDS = ["pk", "external_id", "name", "address", "latitude", "longitude"]
AUTOMATIC_MATCH_STATUSES = [MatchStatus.ACCEPTED, MatchStatus.REVIEW]  # what a run proposes; a person decides the rest
MATCH_EVIDENCE_FIELDS = ["score", "name_score", "distance_m", "same_address", "reason", "evidence"]
MATCH_STATUS_OF_DECISION = {Decision.ACCEPTED: MatchStatus.ACCEPTED, Decision.REVIEW: MatchStatus.REVIEW}
# Fields copied from a staged venue to the published one (the rest identify it).
VENUE_FIELDS = [field.name for field in StagedVenue._meta.fields
                if field.name not in ("id", "run", "source", "external_id")]
GOOGLE_MISSING_REASON = "la ficha de Google ya no está en el archivo"
