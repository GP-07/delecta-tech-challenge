import asyncio
import dataclasses
import functools

import pytest

from libs.crawler.brands import BrandResolver
from libs.crawler.config import CrawlerSettings
from libs.crawler.just_eat.client import VenueNotFoundError
from libs.crawler.just_eat.mapper import VenueMapper
from libs.crawler.service import CrawlService
from libs.crawler.storage import read_partial
from tests.conftest import TIFLIS_ID, TIFLIS_URL

BATCH_SIZE = CrawlerSettings().batch_size


class FakeFetcher:
    """In-memory VenueFetcher: returns recorded sources or raises the configured error per slug."""

    def __init__(self, sources: dict, before_fetch=None):
        self.sources = sources
        self.before_fetch = before_fetch or self._nothing_before_fetch
        self.calls: list[str] = []
        self.in_flight = 0
        self.max_in_flight = 0

    @staticmethod
    def _nothing_before_fetch(slug):
        pass

    async def fetch(self, slug):
        self.before_fetch(slug)
        self.calls.append(slug)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0)  # let the other venues of the batch start
        self.in_flight -= 1
        result = self.sources[slug]
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def partial_path(tmp_path):
    return tmp_path / "venues.partial.jsonl"


def _service(fetcher, partial_path, brands=None):
    return CrawlService(fetcher, VenueMapper(), BrandResolver(brands or {}), partial_path=partial_path,
                        batch_size=BATCH_SIZE)


def _same_venue_under(slugs, source):
    """The same recorded venue served under several slugs, each with its own restaurant id."""
    sources = {}
    for position, slug in enumerate(slugs):
        manifest = source.manifest.model_copy(update={"restaurant_id": str(position)})
        sources[slug] = dataclasses.replace(source, manifest=manifest)
    return sources


def note_partial_results_before(watched_slug, partial_path, on_disk, slug):
    """Before `watched_slug` is fetched, notes the venues already saved to the partial file."""
    if slug == watched_slug:
        on_disk.extend(read_partial(partial_path))


def _url(slug):
    return f"https://www.just-eat.es/restaurants-{slug}/menu"


async def test_crawls_venues_keyed_by_restaurant_id(tiflis_source, tiflis_expected, partial_path):
    service = _service(FakeFetcher({"tiflis-restaurant-barcelona": tiflis_source}), partial_path)

    report = await service.run([TIFLIS_URL])

    assert report.venues == {TIFLIS_ID: tiflis_expected}
    assert report.failures == {}


async def test_applies_brand_mapping(tiflis_source, partial_path):
    service = _service(FakeFetcher({"tiflis-restaurant-barcelona": tiflis_source}), partial_path,
                       brands={"tiflis-restaurant-barcelona": "Tiflis Group"})

    report = await service.run([TIFLIS_URL])

    assert report.venues[TIFLIS_ID]["brand"] == "Tiflis Group"


async def test_a_failing_venue_does_not_stop_the_others(tiflis_source, partial_path):
    fetcher = FakeFetcher({"tiflis-restaurant-barcelona": tiflis_source, "gone": VenueNotFoundError("gone")})

    report = await _service(fetcher, partial_path).run([
        TIFLIS_URL,
        "https://www.just-eat.es/restaurants-gone/menu",
        "https://www.just-eat.es/not-a-venue-page",
    ])

    assert list(report.venues) == [TIFLIS_ID]
    assert list(report.failures) == [
        "https://www.just-eat.es/restaurants-gone/menu",
        "https://www.just-eat.es/not-a-venue-page",
    ]
    assert report.failures["https://www.just-eat.es/restaurants-gone/menu"].startswith("VenueNotFoundError")


async def test_crawls_in_batches_keeping_the_input_order(tiflis_source, partial_path):
    slugs = [f"venue-{position}" for position in range(BATCH_SIZE * 2 + 1)]
    fetcher = FakeFetcher(_same_venue_under(slugs, tiflis_source))

    report = await _service(fetcher, partial_path).run([_url(slug) for slug in slugs])

    assert fetcher.max_in_flight == BATCH_SIZE
    assert list(report.venues) == [str(position) for position in range(len(slugs))]


async def test_saves_partial_results_after_every_batch(tiflis_source, partial_path):
    slugs = [f"venue-{position}" for position in range(BATCH_SIZE + 1)]
    on_disk_when_last_batch_starts = []
    before_fetch = functools.partial(note_partial_results_before, slugs[-1], partial_path,
                                     on_disk_when_last_batch_starts)
    fetcher = FakeFetcher(_same_venue_under(slugs, tiflis_source), before_fetch)

    await _service(fetcher, partial_path).run([_url(slug) for slug in slugs])

    assert on_disk_when_last_batch_starts == [str(position) for position in range(BATCH_SIZE)]
    assert list(read_partial(partial_path)) == [str(position) for position in range(len(slugs))]
