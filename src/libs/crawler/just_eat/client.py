"""HTTP access to the public JSON resources the Just Eat web app itself loads for a venue page.

The venue page (www.just-eat.es) is behind Cloudflare bot protection; this client does NOT try to get
around it. It reads the menu CDN and the public menu API instead, which serve the same data.
"""

import asyncio
import json
import logging
from typing import Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from libs.crawler.config import CrawlerSettings
from libs.crawler.constants import (
    CATALOGUE_FILE,
    CDN_BASE_URL,
    DYNAMIC_BASE_URL,
    MAX_BACKOFF_SECONDS,
    POSTCODE,
    REQUESTS_PER_VENUE,
    RESTAURANT_ID,
)
from libs.crawler.just_eat.schemas import DynamicMenu, ItemDetails, ItemsPayload, Listing, Manifest, VenueSource

logger = logging.getLogger(__name__)

Model = TypeVar("Model", bound=BaseModel)


class JustEatError(Exception):
    pass


class VenueNotFoundError(JustEatError):
    pass


class ResponseTooLargeError(JustEatError):
    pass


class UnexpectedPayloadError(JustEatError):
    pass


class VenueFetcher(Protocol):
    async def fetch(self, slug: str) -> VenueSource: ...


def _is_transient(error: BaseException) -> bool:
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code == 429 or error.response.status_code >= 500
    return isinstance(error, httpx.TransportError)


class JustEatClient:
    def __init__(self, http: httpx.AsyncClient, settings: CrawlerSettings) -> None:
        self._http = http
        self._settings = settings
        # postcode -> {restaurant id: cuisines}; one download per postcode and run, shared by concurrent venues.
        self._listings: dict[str, asyncio.Task[dict[str, list[str]]]] = {}

    async def fetch(self, slug: str) -> VenueSource:
        manifest = await self._get(Manifest, f"{CDN_BASE_URL}/{slug}_es_manifest.json")
        self._check_references(manifest)
        items, item_details, dynamic, listing_cuisines = await asyncio.gather(
            self._get(ItemsPayload, f"{CDN_BASE_URL}/{manifest.items_url}"),
            self._get(ItemDetails, f"{CDN_BASE_URL}/{manifest.item_details_url}"),
            self._get(DynamicMenu, f"{DYNAMIC_BASE_URL}/restaurant/es/{manifest.restaurant_id}/menu/dynamic"),
            self._listing_cuisines(manifest),
        )
        return VenueSource(
            manifest=manifest, items=items, item_details=item_details, dynamic=dynamic,
            listing_cuisines=listing_cuisines,
        )

    async def _listing_cuisines(self, manifest: Manifest) -> list[str] | None:
        """Cuisines of the venue in its postcode listing, or None (not listed, or listing unavailable).

        Venues that are temporarily offline are not listed; the caller then falls back to the manifest.
        """
        postcode = manifest.restaurant_info.location.post_code or ""
        if not POSTCODE.match(postcode):
            logger.warning("restaurant=%s unexpected postcode %r, listing skipped", manifest.restaurant_id, postcode)
            return None
        if postcode not in self._listings:
            self._listings[postcode] = asyncio.create_task(self._download_listing(postcode))
        try:
            listing = await self._listings[postcode]
        except (JustEatError, httpx.HTTPError) as error:
            logger.warning("listing for %s unavailable (%s), cuisines from manifest",
                           postcode, error.__class__.__name__)
            return None
        return listing.get(manifest.restaurant_id)

    async def _download_listing(self, postcode: str) -> dict[str, list[str]]:
        url = f"{DYNAMIC_BASE_URL}/discovery/es/restaurants/enriched/bypostcode/{postcode}"
        listing = await self._get(Listing, url)
        return {restaurant.id: [cuisine.unique_name for cuisine in restaurant.cuisines]
                for restaurant in listing.restaurants}

    @staticmethod
    def _check_references(manifest: Manifest) -> None:
        if not RESTAURANT_ID.match(manifest.restaurant_id):
            raise UnexpectedPayloadError(f"Unexpected restaurant id {manifest.restaurant_id!r}")
        for name in (manifest.items_url, manifest.item_details_url):
            if not CATALOGUE_FILE.match(name):
                raise UnexpectedPayloadError(f"Unexpected catalogue file name {name!r}")

    async def _get(self, model: type[Model], url: str) -> Model:
        retrying = AsyncRetrying(
            stop=stop_after_attempt(self._settings.max_retries),
            wait=wait_exponential(multiplier=self._settings.backoff_seconds, max=MAX_BACKOFF_SECONDS),
            retry=retry_if_exception(_is_transient),
            reraise=True,
        )
        async for attempt in retrying:
            with attempt:
                body = await self._download(url)
        try:
            return model.model_validate(json.loads(body))
        except (ValueError, ValidationError) as error:
            raise UnexpectedPayloadError(f"{url}: {error.__class__.__name__}") from error

    async def _download(self, url: str) -> bytes:
        limit = self._settings.max_response_bytes
        await asyncio.sleep(self._settings.request_delay_seconds)
        async with self._http.stream("GET", url) as response:
            if response.status_code == 404:
                raise VenueNotFoundError(url)
            response.raise_for_status()
            if int(response.headers.get("content-length") or 0) > limit:
                raise ResponseTooLargeError(url)
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > limit:
                    raise ResponseTooLargeError(url)
                chunks.append(chunk)
            return b"".join(chunks)


def build_http_client(settings: CrawlerSettings) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=settings.timeout_seconds,
        headers={"User-Agent": settings.user_agent, "Accept": "application/json"},
        follow_redirects=False,
        # Each venue of a batch makes up to 4 requests at once (items, details, rating, listing).
        limits=httpx.Limits(max_connections=settings.batch_size * REQUESTS_PER_VENUE),
    )
