import functools
import json
from pathlib import Path

import pytest
import respx

from libs.crawler.just_eat.schemas import DynamicMenu, ItemDetails, ItemsPayload, Manifest, VenueSource

FIXTURES = Path(__file__).parent / "fixtures" / "just_eat"
TIFLIS = FIXTURES / "tiflis-restaurant-barcelona"
TIFLIS_URL = "https://www.just-eat.es/restaurants-tiflis-restaurant-barcelona/menu"
TIFLIS_ID = "63038"
GONE_URL = "https://www.just-eat.es/restaurants-gone/menu"


@pytest.fixture(autouse=True)
def output_dir(settings, tmp_path):
    """Every test writes its run folders into its own temporary folder, never into the project's output/."""
    settings.PIPELINE_OUTPUT_DIR = tmp_path / "output"
    return settings.PIPELINE_OUTPUT_DIR


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def serve_recorded_venue(router, slug: str) -> None:
    """Mocks every Just Eat resource of a recorded venue (tests/fixtures/just_eat/{slug})."""
    from libs.crawler.constants import CDN_BASE_URL, DYNAMIC_BASE_URL

    fixtures = FIXTURES / slug
    manifest = load_json(fixtures / "manifest.json")
    router.get(f"{CDN_BASE_URL}/{slug}_es_manifest.json").respond(json=manifest)
    router.get(f"{CDN_BASE_URL}/{manifest['ItemsUrl']}").respond(json=load_json(fixtures / "items.json"))
    router.get(f"{CDN_BASE_URL}/{manifest['ItemDetailsUrl']}").respond(json=load_json(fixtures / "item_details.json"))
    router.get(f"{DYNAMIC_BASE_URL}/restaurant/es/{manifest['RestaurantId']}/menu/dynamic").respond(
        json=load_json(fixtures / "dynamic.json")
    )
    # Recorded while the venue was temporarily offline, so it is not in its postcode listing.
    postcode = manifest["RestaurantInfo"]["Location"]["PostCode"]
    router.get(f"{DYNAMIC_BASE_URL}/discovery/es/restaurants/enriched/bypostcode/{postcode}").respond(
        json={"restaurants": []}
    )


@pytest.fixture
def tiflis_raw() -> dict:
    """Raw payloads exactly as served by Just Eat (recorded)."""
    return {
        "manifest": load_json(TIFLIS / "manifest.json"),
        "items": load_json(TIFLIS / "items.json"),
        "item_details": load_json(TIFLIS / "item_details.json"),
        "dynamic": load_json(TIFLIS / "dynamic.json"),
    }


@pytest.fixture
def tiflis_source(tiflis_raw) -> VenueSource:
    return VenueSource(
        manifest=Manifest.model_validate(tiflis_raw["manifest"]),
        items=ItemsPayload.model_validate(tiflis_raw["items"]),
        item_details=ItemDetails.model_validate(tiflis_raw["item_details"]),
        dynamic=DynamicMenu.model_validate(tiflis_raw["dynamic"]),
    )


@pytest.fixture
def tiflis_expected() -> dict:
    """The venue as it must appear in the output (just_eat_venue_example.json)."""
    return load_json(TIFLIS / "expected_venue.json")


@pytest.fixture
def just_eat(monkeypatch, settings, tmp_path):
    """Just Eat as recorded: Tiflis is served and "gone" no longer exists. The curated URL list is replaced by
    those two venues, the crawler does not pause between requests and runs write into a temporary folder."""
    from libs.crawler.constants import CDN_BASE_URL

    monkeypatch.setattr("libs.crawler.processor.load_venue_urls", functools.partial(list, (TIFLIS_URL, GONE_URL)))
    monkeypatch.setenv("CRAWLER_REQUEST_DELAY_SECONDS", "0")
    monkeypatch.setenv("CRAWLER_BACKOFF_SECONDS", "0")
    settings.PIPELINE_OUTPUT_DIR = tmp_path / "output"
    with respx.mock(assert_all_called=False) as router:
        serve_recorded_venue(router, "tiflis-restaurant-barcelona")
        router.get(f"{CDN_BASE_URL}/gone_es_manifest.json").respond(404)
        yield router
