"""Deletes the staged rows of runs: right after a run is published, and a while after a run failed.

    purge_staged(runs)       deletes the staged rows of some runs
    purge_failed_runs()      staged rows of runs that failed more than PIPELINE_STAGING_RETENTION_DAYS ago
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.menus.models import StagedFoodCategory, StagedMenuItem
from apps.pipeline.models import PipelineRun, Status
from apps.venues.models import StagedVenue, StagedVenueMatch


def purge_staged(runs) -> None:
    """Deletes the staged rows of `runs` (a PipelineRun queryset), children first: the venues are deleted by id,
    never loaded (their menus are large)."""
    StagedMenuItem.objects.filter(run__in=runs).delete()
    StagedFoodCategory.objects.filter(run__in=runs).delete()
    StagedVenueMatch.objects.filter(run__in=runs).delete()
    StagedVenue.objects.filter(run__in=runs).only("pk").delete()


def purge_failed_runs() -> int:
    """Staged rows are kept a while after a failure, for diagnosis; then deleted. Returns how many runs."""
    limit = timezone.now() - timedelta(days=settings.PIPELINE_STAGING_RETENTION_DAYS)
    runs = PipelineRun.objects.filter(status=Status.FAILED, finished_at__lt=limit)
    runs = runs.filter(pk__in=StagedVenue.objects.filter(run__in=runs).values("run"))
    count = runs.count()
    purge_staged(runs)
    return count


def purge_run(run: PipelineRun) -> None:
    purge_staged(PipelineRun.objects.filter(pk=run.pk))
