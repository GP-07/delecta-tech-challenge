"""Stages a run's crawl output ({restaurant_id: venue} as in just_eat_venues.json) as StagedVenue rows.

The published Venue table is not touched: publish_run copies them once every step of the run succeeded.
"""

import logging
from dataclasses import dataclass
from itertools import islice

from django.db import transaction

from apps.pipeline.models import PipelineRun
from apps.venues.constants import JUST_EAT_CHUNK_SIZE
from apps.venues.models import Source, StagedVenue

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class LoadStats:
    staged: int


def load_just_eat_venues(venues: dict[str, dict], *, run: PipelineRun) -> LoadStats:
    """Stages every venue for the run, all or nothing (a step retried by the queue starts again from scratch)."""
    staged = 0
    items = iter(venues.items())
    with transaction.atomic():
        StagedVenue.objects.filter(run=run, source=Source.JUST_EAT).only("pk").delete()  # never load their menus
        while chunk := list(islice(items, JUST_EAT_CHUNK_SIZE)):
            StagedVenue.objects.bulk_create([_to_row(external_id, venue, run) for external_id, venue in chunk])
            staged += len(chunk)
    logger.info("run=%s just eat venues staged: %d", run.pk, staged)
    return LoadStats(staged=staged)


def _to_row(external_id: str, venue: dict, run: PipelineRun) -> StagedVenue:
    address = venue.get("address") or {}
    longitude, latitude = ((address.get("location") or {}).get("coordinates") or [None, None])[:2]
    rating = venue.get("rating") or {}
    return StagedVenue(
        run=run,
        source=Source.JUST_EAT,
        external_id=str(external_id),
        name=venue["name"],
        brand=venue.get("brand"),
        unique_name=venue.get("uniqueName") or "",
        city=address.get("city") or "",
        address=address.get("firstLine") or "",
        postal_code=address.get("postalCode") or "",
        latitude=latitude,
        longitude=longitude,
        rating_count=rating.get("count"),
        star_rating=rating.get("starRating"),
        cuisines=venue.get("cuisines") or [],
        store_front_type=venue.get("storeFrontType") or "",
        is_test=bool(venue.get("isTestRestaurant")),
        url=venue.get("url") or "",
        logo_url=venue.get("logoUrl"),
        description=venue.get("description") or "",
        opening_times=venue.get("openingTimes") or [],
        menus=venue.get("menus") or {},
    )
