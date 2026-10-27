"""Pipeline steps of the venues app."""

from django.conf import settings

from apps.pipeline.models import PipelineRun
from apps.pipeline.steps import StepOutcome
from apps.venues.google_import_services import load_google_venues as load_google_file
from apps.venues.just_eat_import_services import load_just_eat_venues
from apps.venues.matching_services import match_run_venues
from libs.crawler.processor import CrawlJob, CrawlProcessor


def crawl_just_eat(run: PipelineRun) -> StepOutcome:
    """Crawls the curated Just Eat venues into a JSON file, then stages them for the run (StagedVenue).

    Venues that could not be crawled are reported in the metrics (and in the failures file); the step only
    fails when the run as a whole does (e.g. CrawlTimeoutError).
    """
    processor = CrawlProcessor(CrawlJob(output_dir=settings.PIPELINE_OUTPUT_DIR, limit=run.limit))
    result = processor.run_sync()
    loaded = load_just_eat_venues(processor.read_output(), run=run)
    return StepOutcome(
        metrics={
            "requested": result.requested,
            "crawled": result.crawled,
            "failed": result.failed,
            "staged": loaded.staged,
        },
        output_dir=str(result.run_dir),
    )


def load_google_venues(run: PipelineRun) -> StepOutcome:
    """Stages the run's Google venues file, its SHA-256 recorded in the run."""
    return StepOutcome(metrics=load_google_file(run.google_venues_file, run=run).as_metrics())


def match_venues(run: PipelineRun) -> StepOutcome:
    """Links the Just Eat venues crawled by this run to the Google venues."""
    return StepOutcome(metrics=match_run_venues(run).as_metrics())
