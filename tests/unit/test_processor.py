import asyncio
import functools
import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from libs.crawler.config import CrawlerSettings
from libs.crawler.constants import CDN_BASE_URL
from libs.crawler.processor import CrawlJob, CrawlProcessor, CrawlTimeoutError, load_venue_urls
from tests.conftest import TIFLIS, TIFLIS_ID, TIFLIS_URL, load_json, serve_recorded_venue

GONE_URL = "https://www.just-eat.es/restaurants-gone/menu"
SLOW_URL = "https://www.just-eat.es/restaurants-slow/menu"
FAST = CrawlerSettings(request_delay_seconds=0, backoff_seconds=0)
STARTED_AT = datetime(2026, 10, 26, 13, 52, 28, tzinfo=UTC)


@pytest.fixture
def router():
    with respx.mock(assert_all_called=False) as mock:
        serve_recorded_venue(mock, "tiflis-restaurant-barcelona")
        mock.get(f"{CDN_BASE_URL}/gone_es_manifest.json").respond(404)
        yield mock


def fixed_time(moment):
    return moment


def _processor(tmp_path, urls, settings=FAST, started_at=STARTED_AT, **job):
    job = CrawlJob(urls=urls, output_dir=tmp_path, settings=settings, **job)
    return CrawlProcessor(job, clock=functools.partial(fixed_time, started_at))


async def test_each_run_writes_into_its_own_timestamped_folder(router, tmp_path):
    processor = _processor(tmp_path, [TIFLIS_URL])

    result = await processor.run()

    run_dir = tmp_path / "20261026T135228Z"
    assert result.run_dir == processor.run_dir == run_dir
    assert result.output_path == processor.output_path == run_dir / "just_eat_venues.json"
    assert [path.name for path in tmp_path.iterdir()] == ["20261026T135228Z"]


async def test_run_writes_the_output_and_summarises_the_run(router, tmp_path):
    processor = _processor(tmp_path, [TIFLIS_URL])

    result = await processor.run()

    assert result.ok
    assert (result.requested, result.crawled, result.failed, result.total_in_output) == (1, 1, 0, 1)
    assert result.failures_path is None
    assert processor.read_output() == {TIFLIS_ID: load_json(TIFLIS / "expected_venue.json")}
    assert processor.read_failures() == {}


async def test_runs_are_independent_and_never_touch_each_other(router, tmp_path):
    first = _processor(tmp_path, [TIFLIS_URL, GONE_URL])
    await first.run()
    second = _processor(tmp_path, [TIFLIS_URL], started_at=datetime(2026, 10, 27, 9, 0, 0, tzinfo=UTC))
    await second.run()

    assert first.run_dir != second.run_dir
    assert list(first.read_failures()) == [GONE_URL]  # the clean second run did not remove it
    assert list(first.read_output()) == list(second.read_output()) == [TIFLIS_ID]


async def test_runs_started_in_the_same_second_get_different_folders(router, tmp_path):
    first, second = _processor(tmp_path, [TIFLIS_URL]), _processor(tmp_path, [TIFLIS_URL])

    await first.run()
    await second.run()

    assert first.run_dir.name == "20261026T135228Z"
    assert second.run_dir.name == "20261026T135228Z-2"


async def test_paths_are_unknown_until_the_run_starts(tmp_path):
    processor = _processor(tmp_path, [TIFLIS_URL])

    with pytest.raises(RuntimeError):
        _ = processor.output_path


async def test_a_processor_runs_only_once(router, tmp_path):
    processor = _processor(tmp_path, [TIFLIS_URL])
    await processor.run()

    with pytest.raises(RuntimeError):
        await processor.run()


async def test_partial_results_are_removed_once_the_final_file_exists(router, tmp_path):
    processor = _processor(tmp_path, [TIFLIS_URL])

    await processor.run()

    assert sorted(path.name for path in processor.run_dir.iterdir()) == ["just_eat_venues.json"]


def note_whether_the_final_file_exists(processor, seen_while_running, request):
    """Answers the last venue's request (404), noting whether the final file was already written."""
    seen_while_running["final exists"] = processor.output_path.exists()
    return httpx.Response(404)


async def answer_never_until_cancelled(cancelled, request):
    try:
        await asyncio.sleep(60)
    except asyncio.CancelledError:
        cancelled.set()
        raise


async def test_the_final_file_is_only_written_when_the_run_finishes(router, tmp_path):
    processor = _processor(tmp_path, [TIFLIS_URL, GONE_URL])
    seen_while_running = {}
    router.get(f"{CDN_BASE_URL}/gone_es_manifest.json").mock(
        side_effect=functools.partial(note_whether_the_final_file_exists, processor, seen_while_running))

    await processor.run()

    assert seen_while_running == {"final exists": False}
    assert list(processor.read_output()) == [TIFLIS_ID]


async def test_failures_are_reported_and_written_next_to_the_output(router, tmp_path):
    processor = _processor(tmp_path, [TIFLIS_URL, GONE_URL])

    result = await processor.run()

    assert not result.ok
    assert (result.crawled, result.failed, result.total_in_output) == (1, 1, 1)
    assert result.failures_path == processor.failures_path == processor.run_dir / "just_eat_venues.failures.json"
    assert list(processor.read_failures()) == [GONE_URL]


async def test_a_stalled_run_fails_after_the_timeout_and_cancels_its_requests(router, tmp_path):
    cancelled = asyncio.Event()
    router.get(f"{CDN_BASE_URL}/slow_es_manifest.json").mock(
        side_effect=functools.partial(answer_never_until_cancelled, cancelled))
    # batch_size 1: Tiflis in a first batch, the stalled venue after
    settings = CrawlerSettings(request_delay_seconds=0, run_timeout_seconds=0.2, batch_size=1)
    processor = _processor(tmp_path, [TIFLIS_URL, SLOW_URL], settings=settings)

    with pytest.raises(CrawlTimeoutError):
        await processor.run()

    assert cancelled.is_set()
    assert not processor.output_path.exists()  # a failed run never produces the final file
    assert list(processor.read_partial()) == [TIFLIS_ID]  # kept to inspect what was done


async def test_urls_are_deduplicated_and_limited(router, tmp_path):
    result = await _processor(tmp_path, [TIFLIS_URL, TIFLIS_URL, GONE_URL], limit=1).run()

    assert (result.requested, result.crawled, result.failed) == (1, 1, 0)


async def test_custom_brands_file(router, tmp_path):
    brands = tmp_path / "brands.json"
    brands.write_text(json.dumps({"tiflis-restaurant-barcelona": "Tiflis Group"}))
    processor = _processor(tmp_path / "runs", [TIFLIS_URL], brands_file=brands)

    await processor.run()

    assert processor.read_output()[TIFLIS_ID]["brand"] == "Tiflis Group"


def test_run_sync_for_synchronous_workers(router, tmp_path):
    result = _processor(tmp_path, [TIFLIS_URL]).run_sync()

    assert result.crawled == 1


def test_venue_urls_come_from_the_curated_file_in_the_project():
    urls = load_venue_urls()

    assert len(urls) == 2696
    assert urls[0] == "https://www.just-eat.es/restaurants-edo/menu"


def test_a_job_crawls_the_curated_urls_by_default(tmp_path):
    assert list(CrawlJob(output_dir=tmp_path).urls) == load_venue_urls()
