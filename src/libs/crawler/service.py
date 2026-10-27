"""Use case: crawl a list of Just Eat venue URLs."""

import asyncio
import logging
from dataclasses import dataclass, field
from itertools import batched
from pathlib import Path

from libs.crawler.brands import BrandResolver
from libs.crawler.just_eat.client import VenueFetcher
from libs.crawler.just_eat.mapper import VenueMapper
from libs.crawler.just_eat.url import slug_from_url
from libs.crawler.storage import append_partial

logger = logging.getLogger(__name__)


@dataclass
class CrawlReport:
    venues: dict[str, dict] = field(default_factory=dict)  # restaurant id -> venue (output format), input order
    failures: dict[str, str] = field(default_factory=dict)  # url -> reason


class CrawlService:
    """Crawls URLs as fast as it politely can: `batch_size` venues at a time, saving partial results as it goes."""

    def __init__(self, fetcher: VenueFetcher, mapper: VenueMapper, brands: BrandResolver, *, partial_path: Path,
                 batch_size: int):
        self._fetcher = fetcher
        self._mapper = mapper
        self._brands = brands
        self._partial_path = partial_path
        self._batch_size = batch_size

    async def run(self, urls: list[str]) -> CrawlReport:
        report = CrawlReport()
        for batch in batched(urls, self._batch_size):
            # The only concurrency: the venues of one batch are crawled at the same time.
            results = await asyncio.gather(*(self._crawl_venue(url) for url in batch), return_exceptions=True)
            batch_venues = self._record(report, batch, results)
            append_partial(self._partial_path, batch_venues)
            logger.info("crawled %d/%d urls, %d failed", len(report.venues) + len(report.failures),
                        len(urls), len(report.failures))
        return report

    async def _crawl_venue(self, url: str) -> tuple[str, dict]:
        slug = slug_from_url(url)
        source = await self._fetcher.fetch(slug)
        venue = self._mapper.map(source, url=url, brand=self._brands.resolve(slug))
        return source.manifest.restaurant_id, venue.model_dump()

    @staticmethod
    def _record(report: CrawlReport, urls: tuple[str, ...], results: list) -> dict[str, dict]:
        """Adds a batch's results to the report; returns the venues it crawled."""
        batch_venues = {}
        for url, result in zip(urls, results, strict=True):
            if isinstance(result, Exception):
                logger.error("crawl failed url=%s error=%s: %s", url, result.__class__.__name__, result)
                report.failures[url] = f"{result.__class__.__name__}: {result}"
            else:
                restaurant_id, venue = result
                batch_venues[restaurant_id] = venue
        report.venues |= batch_venues
        return batch_venues
