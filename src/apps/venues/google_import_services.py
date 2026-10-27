"""Stages the run's Google venues file (google_venues.json: a list of places) as StagedVenue rows.

Every run loads its own file (PipelineRun.google_venues_file) and records its SHA-256: the matching of the run
only uses the places of that file. publish_run then replaces the published Google venues with them.

The file is untrusted input: its size is capped and every record is validated; a single invalid record rejects
the whole file.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.db import transaction
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from apps.pipeline.file_helpers import file_sha256
from apps.pipeline.models import PipelineRun
from apps.venues.constants import GOOGLE_CHUNK_SIZE, GOOGLE_DETAIL_FIELDS, POSTAL_CODE
from apps.venues.models import Source, StagedVenue

logger = logging.getLogger(__name__)


class GoogleVenuesFileError(Exception):
    """The file is missing, too large or not a valid list of Google places."""


class GooglePlace(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    place_id: str = Field(alias="googlePlaceId", pattern=r"^[A-Za-z0-9_-]{10,255}$")
    name: str = Field(min_length=1, max_length=255)
    raw_address: str | None = Field(alias="rawAddress", default=None, max_length=255)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    rating: float | None = Field(default=None, ge=0, le=5)
    total_reviews: int | None = Field(alias="totalReviews", default=None, ge=0)
    maps_url: str | None = Field(alias="googleMapsUrl", default=None, max_length=500, pattern=r"^https://")
    description: str | None = None


_PLACES = TypeAdapter(list[GooglePlace])


@dataclass(frozen=True)
class GoogleLoadResult:
    sha256: str
    places: int  # distinct places in the file
    duplicates: int  # records repeating a place id already in the file (the first one is kept)

    def as_metrics(self) -> dict:
        return dict(self.__dict__)


def load_google_venues(path: str | Path, *, run: PipelineRun) -> GoogleLoadResult:
    path = _checked(path)
    sha256 = file_sha256(path)
    run.google_venues_sha256 = sha256
    run.save(update_fields=["google_venues_sha256"])
    places, duplicates = _read(path)
    with transaction.atomic():
        StagedVenue.objects.filter(run=run, source=Source.GOOGLE).only("pk").delete()
        rows = [_to_row(place, run) for place in places]
        for start in range(0, len(rows), GOOGLE_CHUNK_SIZE):
            StagedVenue.objects.bulk_create(rows[start:start + GOOGLE_CHUNK_SIZE])
    result = GoogleLoadResult(sha256=sha256, places=len(places), duplicates=duplicates)
    logger.info("run=%s google venues staged from %s: %s", run.pk, path, result)
    return result


def _checked(path: str | Path) -> Path:
    if not path:
        raise GoogleVenuesFileError("no Google venues file configured (GOOGLE_VENUES_FILE)")
    path = Path(path)
    if not path.is_file():
        raise GoogleVenuesFileError(f"Google venues file not found: {path}")
    if path.stat().st_size > settings.GOOGLE_VENUES_MAX_BYTES:
        raise GoogleVenuesFileError(f"Google venues file larger than {settings.GOOGLE_VENUES_MAX_BYTES} bytes")
    return path


def _read(path: Path) -> tuple[list[GooglePlace], int]:
    try:
        places = _PLACES.validate_python(json.loads(path.read_bytes()))
    except (ValueError, ValidationError) as error:
        raise GoogleVenuesFileError(f"invalid Google venues file: {_summary(error)}") from error
    unique = list({place.place_id: place for place in reversed(places)}.values())[::-1]  # first wins
    return unique, len(places) - len(unique)


def _summary(error: Exception) -> str:
    if isinstance(error, ValidationError):
        first_error = error.errors()[0]
        return f"{error.error_count()} errors, first at {first_error['loc']}: {first_error['msg']}"
    return error.__class__.__name__


def _to_row(place: GooglePlace, run: PipelineRun) -> StagedVenue:
    extra = place.model_extra or {}
    return StagedVenue(
        run=run,
        source=Source.GOOGLE,
        external_id=place.place_id,
        name=place.name,
        address=place.raw_address or "",
        postal_code=_postal_code(place.raw_address),
        latitude=place.latitude,
        longitude=place.longitude,
        star_rating=place.rating,
        rating_count=place.total_reviews,
        url=place.maps_url or "",
        description=place.description or "",
        details={key: extra.get(key) for key in GOOGLE_DETAIL_FIELDS},
    )


def _postal_code(address: str | None) -> str:
    match = POSTAL_CODE.search(address or "")
    return match.group(1) if match else ""
