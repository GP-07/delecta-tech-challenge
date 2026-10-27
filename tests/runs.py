"""Runs taken step by step, without the queue: each helper does the work of the steps and marks them succeeded."""

from django.conf import settings

from apps.menus.categorization_services import categorize_run_items
from apps.menus.publish_services import publish_run
from apps.pipeline.models import PipelineRun, Status
from apps.pipeline.run_services import create_run
from apps.venues.google_import_services import load_google_venues
from apps.venues.just_eat_import_services import load_just_eat_venues
from apps.venues.matching_services import match_run_venues


def succeeded(run: PipelineRun, *names: str, **fields) -> None:
    run.steps.filter(name__in=names).update(status=Status.SUCCEEDED, **fields)


def staged_run(venues: dict, *, google_file=None, crawl_dir="") -> PipelineRun:
    """A run whose crawl staged `venues` ({restaurant id: venue}) and whose Google load staged `google_file`."""
    run = create_run(google_venues_file=str(google_file or settings.GOOGLE_VENUES_FILE))
    load_just_eat_venues(venues, run=run)
    succeeded(run, "crawl_just_eat", output_dir=str(crawl_dir))
    load_google_venues(run.google_venues_file, run=run)
    succeeded(run, "load_google_venues")
    return run


def matched_run(venues: dict, **kwargs) -> PipelineRun:
    run = staged_run(venues, **kwargs)
    match_run_venues(run)
    succeeded(run, "match_venues")
    return run


def categorized_run(venues: dict, *, embedder=None, **kwargs) -> PipelineRun:
    run = matched_run(venues, **kwargs)
    categorize_run_items(run, embedder=embedder)
    succeeded(run, "categorize_menu_items")
    return run


def published_run(venues: dict, **kwargs) -> PipelineRun:
    run = categorized_run(venues, **kwargs)
    publish_run(run)
    succeeded(run, "publish_run")
    PipelineRun.objects.filter(pk=run.pk).update(status=Status.SUCCEEDED)
    run.refresh_from_db()
    return run
