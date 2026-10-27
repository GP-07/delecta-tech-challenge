"""Crawl process: the single entry point to run a crawl job, from a CLI, a task queue or a notebook.

    processor = CrawlProcessor(CrawlJob(output_dir=Path("output")))   # URLs: data/just_eat_urls.json
    result = processor.run_sync()        # or: await processor.run()
    processor.run_dir                    # output/20261026T135228Z
    processor.read_output()              # {restaurant_id: venue}
    processor.read_failures()            # {url: reason}

Every run gets its own folder under `output_dir`, named after its start time (UTC), so runs are independent
and never overwrite or delete each other's files:

    output/20261026T135228Z/
        just_eat_venues.json             final output, written when the run finishes
        just_eat_venues.partial.jsonl    results so far, appended after every batch; removed once the final exists
        just_eat_venues.failures.json    {url: reason}, only if some URLs failed

Steps, in order:
    1. select the URLs to crawl (dedupe, limit)
    2. create the run folder
    3. crawl them (CrawlService: in batches, appending each batch to the partial file)
    4. write the final output and remove the partial file
    5. write the failures file, if any

Every run reprocesses all its URLs. A run that exceeds `settings.run_timeout_seconds` is cancelled (including
its in-flight requests) and raises CrawlTimeoutError: it never produces the final file, and its partial file
is kept for inspection. The way forward is a new, full run.
"""

import asyncio
import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

from libs.crawler.brands import BrandResolver
from libs.crawler.config import CrawlerSettings
from libs.crawler.constants import MAX_RUN_DIR_ATTEMPTS, OUTPUT_NAME, RUN_DIR_FORMAT
from libs.crawler.just_eat.client import JustEatClient, build_http_client
from libs.crawler.just_eat.mapper import VenueMapper
from libs.crawler.service import CrawlReport, CrawlService
from libs.crawler.storage import read_partial, read_venues, write_venues

logger = logging.getLogger(__name__)

class CrawlTimeoutError(Exception):
    """The run took longer than allowed and was cancelled. It must be reprocessed from scratch."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def load_venue_urls() -> list[str]:
    """The venues to crawl: the curated src/crawler/data/just_eat_urls.json ({id: url})."""
    content = resources.files("libs.crawler.data").joinpath("just_eat_urls.json").read_text(encoding="utf-8")
    return list(json.loads(content).values())


def default_venue_urls() -> list[str]:
    """Default of CrawlJob.urls. Calls load_venue_urls through this module, so a test can replace it."""
    return load_venue_urls()


@dataclass(frozen=True)
class CrawlJob:
    """What to crawl and where to store it. Plain data, so it can travel through a task queue."""

    output_dir: Path  # base folder; each run creates its own sub-folder in it
    urls: Sequence[str] = field(default_factory=default_venue_urls)  # looked up when the job is created
    limit: int | None = None  # only the first N URLs
    brands_file: Path | None = None  # {uniqueName: brand}; default: the bundled reference file
    settings: CrawlerSettings = field(default_factory=CrawlerSettings.from_env)


@dataclass(frozen=True)
class CrawlResult:
    run_dir: Path
    output_path: Path
    failures_path: Path | None  # None when every URL was crawled
    requested: int  # URLs after dedupe and limit
    crawled: int
    failed: int
    total_in_output: int

    @property
    def ok(self) -> bool:
        return self.failed == 0


class CrawlProcessor:
    """One crawl run. Create a new processor for every run."""

    def __init__(self, job: CrawlJob, *, clock: Callable[[], datetime] = utc_now) -> None:
        self.job = job
        self._clock = clock
        self._run_dir: Path | None = None

    # --- where the output is (known once the run has started) -----------------------------------

    @property
    def run_dir(self) -> Path:
        if self._run_dir is None:
            raise RuntimeError("the run has not started yet")
        return self._run_dir

    @property
    def output_path(self) -> Path:
        """Final output; only written when the run finishes."""
        return self.run_dir / f"{OUTPUT_NAME}.json"

    @property
    def partial_path(self) -> Path:
        """Results so far while the run is in progress (kept if the run timed out)."""
        return self.run_dir / f"{OUTPUT_NAME}.partial.jsonl"

    @property
    def failures_path(self) -> Path:
        return self.run_dir / f"{OUTPUT_NAME}.failures.json"

    def read_output(self) -> dict:
        """{restaurant_id: venue} of this run, once finished."""
        return read_venues(self.output_path)

    def read_partial(self) -> dict:
        """{restaurant_id: venue} crawled so far by this run, while in progress or after a timeout."""
        return read_partial(self.partial_path)

    def read_failures(self) -> dict[str, str]:
        """{url: reason} of this run; empty if it had no failures."""
        if not self.failures_path.exists():
            return {}
        return json.loads(self.failures_path.read_text(encoding="utf-8"))

    # --- run ----------------------------------------------------------------------------------------

    def run_sync(self) -> CrawlResult:
        """For synchronous callers (e.g. a Celery/RQ worker). Must not be called from a running event loop."""
        return asyncio.run(self.run())

    async def run(self) -> CrawlResult:
        if self._run_dir is not None:
            raise RuntimeError("a processor runs only once; create a new one for a new run")
        urls = self._select_urls()
        self._run_dir = self._create_run_dir()
        logger.info("urls=%d run_dir=%s", len(urls), self.run_dir)

        report = await self._crawl_with_timeout(urls)
        self._publish(report.venues)
        self._write_failures(report)

        result = CrawlResult(
            run_dir=self.run_dir,
            output_path=self.output_path,
            failures_path=self.failures_path if report.failures else None,
            requested=len(urls),
            crawled=len(report.venues),
            failed=len(report.failures),
            total_in_output=len(report.venues),
        )
        logger.info("crawled=%d failed=%d output=%s", result.crawled, result.failed, result.output_path)
        return result

    def _select_urls(self) -> list[str]:
        urls = list(dict.fromkeys(self.job.urls))  # dedupe, keep order
        return urls[: self.job.limit] if self.job.limit else urls

    def _create_run_dir(self) -> Path:
        """output_dir/<start time UTC>, with a -2, -3… suffix if another run started in the same second."""
        base = Path(self.job.output_dir)
        base.mkdir(parents=True, exist_ok=True)
        name = self._clock().astimezone(UTC).strftime(RUN_DIR_FORMAT)
        for attempt in range(1, MAX_RUN_DIR_ATTEMPTS):
            run_dir = base / (name if attempt == 1 else f"{name}-{attempt}")
            try:
                run_dir.mkdir()  # atomic: two runs can never get the same folder
            except FileExistsError:
                continue
            return run_dir
        raise RuntimeError(f"could not create a run folder for {name} in {base}")

    async def _crawl_with_timeout(self, urls: list[str]) -> CrawlReport:
        timeout = self.job.settings.run_timeout_seconds
        try:
            async with asyncio.timeout(timeout):
                return await self._crawl(urls)
        except TimeoutError as error:
            logger.error("run timed out after %ss, cancelled; partial results kept in %s", timeout, self.partial_path)
            raise CrawlTimeoutError(f"crawl run exceeded {timeout}s") from error

    async def _crawl(self, urls: list[str]) -> CrawlReport:
        settings = self.job.settings
        async with build_http_client(settings) as http:
            service = CrawlService(JustEatClient(http, settings), VenueMapper(), self._brands(),
                                   partial_path=self.partial_path, batch_size=settings.batch_size)
            return await service.run(urls)

    def _publish(self, venues: dict) -> None:
        """Writes the final output, then removes the partial results."""
        write_venues(self.output_path, venues)
        self.partial_path.unlink(missing_ok=True)

    def _brands(self) -> BrandResolver:
        return BrandResolver.from_file(self.job.brands_file) if self.job.brands_file else BrandResolver.default()

    def _write_failures(self, report: CrawlReport) -> None:
        if report.failures:
            self.failures_path.write_text(json.dumps(report.failures, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.warning("failures written to %s", self.failures_path)

