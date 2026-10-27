"""Celery entry points. Thin on purpose: they only carry ids; all the logic is in run_services."""

from celery import shared_task
from django.conf import settings
from django.utils.module_loading import import_string

from apps.pipeline import run_services


@shared_task(name="pipeline.dispatch_waiting_runs")
def dispatch_waiting_runs() -> list[int]:
    return run_services.dispatch_waiting_runs()


@shared_task(name="pipeline.run_step")
def run_step(step_id: int) -> None:
    run_services.execute_step(step_id)


@shared_task(name="pipeline.fail_stalled_steps")
def fail_stalled_steps() -> int:
    return run_services.fail_stalled_steps()


@shared_task(name="pipeline.purge_staged_runs")
def purge_staged_runs() -> int:
    """Deletes the staged rows of runs that failed long ago (settings.PIPELINE_STAGING_CLEANUP)."""
    return import_string(settings.PIPELINE_STAGING_CLEANUP)()
