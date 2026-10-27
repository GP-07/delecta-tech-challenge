import json

import httpx
import pytest
import respx

from libs.crawler.config import CrawlerSettings
from libs.crawler.constants import CDN_BASE_URL, DYNAMIC_BASE_URL
from libs.crawler.just_eat.client import (
    JustEatClient,
    ResponseTooLargeError,
    UnexpectedPayloadError,
    VenueNotFoundError,
)
from tests.conftest import TIFLIS_ID

SLUG = "tiflis-restaurant-barcelona"
MANIFEST_URL = f"{CDN_BASE_URL}/{SLUG}_es_manifest.json"
ITEMS_URL = f"{CDN_BASE_URL}/{SLUG}_es_items.json"
DETAILS_URL = f"{CDN_BASE_URL}/{SLUG}_es_itemDetails.json"
DYNAMIC_URL = f"{DYNAMIC_BASE_URL}/restaurant/es/{TIFLIS_ID}/menu/dynamic"
LISTING_URL = f"{DYNAMIC_BASE_URL}/discovery/es/restaurants/enriched/bypostcode/08013"

FAST = CrawlerSettings(max_retries=3, backoff_seconds=0, request_delay_seconds=0)


def _listing(*restaurants):
    return {"restaurants": [{"id": restaurant_id, "cuisines": [{"name": cuisine, "uniqueName": cuisine}
                                                               for cuisine in cuisines]}
                            for restaurant_id, cuisines in restaurants]}


def _mock_venue(router, raw, listing=None):
    router.get(MANIFEST_URL).respond(json=raw["manifest"])
    router.get(ITEMS_URL).respond(json=raw["items"])
    router.get(DETAILS_URL).respond(json=raw["item_details"])
    router.get(DYNAMIC_URL).respond(json=raw["dynamic"])
    return router.get(LISTING_URL).respond(json=listing or _listing(("1", ["pizza"])))


async def _fetch(slug=SLUG, settings=FAST):
    async with httpx.AsyncClient() as http:
        return await JustEatClient(http, settings).fetch(slug)


@respx.mock
async def test_takes_cuisines_from_the_postcode_listing(tiflis_raw):
    _mock_venue(respx, tiflis_raw, listing=_listing(("1", ["pizza"]), (TIFLIS_ID, ["medio-oriente", "lo-mas-top"])))

    source = await _fetch()

    assert source.listing_cuisines == ["medio-oriente", "lo-mas-top"]


@respx.mock
async def test_venue_missing_from_the_listing_has_no_listing_cuisines(tiflis_raw):
    _mock_venue(respx, tiflis_raw)  # e.g. temporarily offline venues are not listed

    source = await _fetch()

    assert source.listing_cuisines is None


@respx.mock
async def test_listing_is_downloaded_once_per_postcode(tiflis_raw):
    listing_route = _mock_venue(respx, tiflis_raw)

    async with httpx.AsyncClient() as http:
        client = JustEatClient(http, FAST)
        await client.fetch(SLUG)
        await client.fetch(SLUG)

    assert listing_route.call_count == 1


@respx.mock
async def test_listing_failure_does_not_fail_the_venue(tiflis_raw):
    _mock_venue(respx, tiflis_raw)
    respx.get(LISTING_URL).respond(500)

    source = await _fetch()

    assert source.listing_cuisines is None
    assert source.manifest.restaurant_id == TIFLIS_ID


@respx.mock
async def test_unexpected_postcode_is_never_put_in_a_url(tiflis_raw):
    manifest = json.loads(json.dumps(tiflis_raw["manifest"]))
    manifest["RestaurantInfo"]["Location"]["PostCode"] = "../admin"
    listing_route = _mock_venue(respx, {**tiflis_raw, "manifest": manifest})

    source = await _fetch()

    assert source.listing_cuisines is None
    assert listing_route.call_count == 0


@respx.mock
async def test_fetches_the_four_resources_of_a_venue(tiflis_raw):
    _mock_venue(respx, tiflis_raw)

    source = await _fetch()

    assert source.manifest.restaurant_id == TIFLIS_ID
    assert len(source.items.items) == 89
    assert source.dynamic.restaurant_rating.rating_count == 18


@respx.mock
async def test_retries_transient_errors(tiflis_raw):
    _mock_venue(respx, tiflis_raw)
    route = respx.get(MANIFEST_URL)
    route.side_effect = [
        httpx.Response(503),
        httpx.ConnectTimeout("t"),
        httpx.Response(200, json=tiflis_raw["manifest"]),
    ]

    source = await _fetch()

    assert source.manifest.restaurant_id == TIFLIS_ID
    assert route.call_count == 3


@respx.mock
async def test_gives_up_after_max_retries():
    route = respx.get(MANIFEST_URL).respond(429)

    with pytest.raises(httpx.HTTPStatusError):
        await _fetch()
    assert route.call_count == FAST.max_retries


@respx.mock
async def test_unknown_venue_is_not_retried():
    route = respx.get(MANIFEST_URL).respond(404)

    with pytest.raises(VenueNotFoundError):
        await _fetch()
    assert route.call_count == 1


@respx.mock
async def test_rejects_oversized_responses(tiflis_raw):
    respx.get(MANIFEST_URL).respond(json=tiflis_raw["manifest"])

    with pytest.raises(ResponseTooLargeError):
        await _fetch(settings=CrawlerSettings(max_response_bytes=1_000, backoff_seconds=0))


@respx.mock
async def test_rejects_catalogue_file_names_that_could_escape_the_cdn(tiflis_raw):
    manifest = {**tiflis_raw["manifest"], "ItemsUrl": "../../evil.json"}
    respx.get(MANIFEST_URL).respond(json=manifest)

    with pytest.raises(UnexpectedPayloadError):
        await _fetch()


@respx.mock
async def test_accepts_slugs_with_underscores(tiflis_raw):
    # e.g. dona_tota-poblenou-barcelona and condis_zona-franca-barcelona in just_eat_urls.json
    slug = "dona_tota-poblenou-barcelona"
    manifest = {**tiflis_raw["manifest"], "ItemsUrl": f"{slug}_es_items.json",
                "ItemDetailsUrl": f"{slug}_es_itemDetails.json"}
    _mock_venue(respx, tiflis_raw)
    respx.get(f"{CDN_BASE_URL}/{slug}_es_manifest.json").respond(json=manifest)
    respx.get(f"{CDN_BASE_URL}/{slug}_es_items.json").respond(json=tiflis_raw["items"])
    respx.get(f"{CDN_BASE_URL}/{slug}_es_itemDetails.json").respond(json=tiflis_raw["item_details"])

    source = await _fetch(slug)

    assert len(source.items.items) == 89


@respx.mock
async def test_rejects_payloads_that_do_not_match_the_schema():
    respx.get(MANIFEST_URL).respond(json={"unexpected": True})

    with pytest.raises(UnexpectedPayloadError):
        await _fetch()
