import pytest

from apps.pipeline.run_services import create_run
from apps.venues.models import StagedVenue, Venue
from apps.venues.steps import crawl_just_eat
from libs.crawler.processor import CrawlTimeoutError
from tests.conftest import TIFLIS_ID

pytestmark = pytest.mark.django_db


def test_crawl_writes_the_run_files_and_stages_the_venues(just_eat, settings):
    run = create_run()

    outcome = crawl_just_eat(run)

    assert outcome.metrics == {"requested": 2, "crawled": 1, "failed": 1, "staged": 1}
    assert outcome.output_dir.startswith(str(settings.PIPELINE_OUTPUT_DIR))
    assert list(StagedVenue.objects.values_list("external_id", "run")) == [(TIFLIS_ID, run.pk)]
    assert not Venue.objects.exists()


def test_crawl_honours_the_run_limit(just_eat):
    outcome = crawl_just_eat(create_run(limit=1))

    assert (outcome.metrics["requested"], outcome.metrics["failed"]) == (1, 0)


def test_a_crawl_that_times_out_fails_the_step_and_loads_nothing(just_eat, monkeypatch):
    monkeypatch.setenv("CRAWLER_RUN_TIMEOUT_SECONDS", "0")

    with pytest.raises(CrawlTimeoutError):
        crawl_just_eat(create_run())

    assert not StagedVenue.objects.exists()
