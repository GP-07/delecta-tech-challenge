"""The life of pipeline runs. The changes of status of each step are in transition_services.

    create_run()              a new WAITING run, with one WAITING step per configured step
    dispatch_waiting_runs()   WAITING runs -> QUEUED, their first step sent to the queue (daily, by Celery beat)
    execute_step(step_id)     runs a QUEUED step; success queues the next step (or finishes the run),
                              failure fails the step and the run with the error message
    fail_stalled_steps()      steps lost on the way (never picked up, or their worker died) -> FAILED
    retry_run(run)            a failed run is never resumed: a new WAITING run is created instead

Messages are only sent to the queue after the transaction that changed the status commits.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.pipeline.constants import STALLED_RUNNING_GRACE_SECONDS
from apps.pipeline.models import PipelineRun, Status, StepRun
from apps.pipeline.steps import get_handler, step_names
from apps.pipeline.transition_services import StepTransition

logger = logging.getLogger(__name__)


@transaction.atomic
def create_run(*, limit: int | None = None, google_venues_file: str | None = None,
               food_categories_file: str | None = None) -> PipelineRun:
    """The input files are fixed when the run is created: settings.GOOGLE_VENUES_FILE and
    settings.FOOD_CATEGORIES_FILE unless given."""
    run = PipelineRun.objects.create(
        limit=limit, google_venues_file=str(google_venues_file or settings.GOOGLE_VENUES_FILE),
        food_categories_file=str(food_categories_file or settings.FOOD_CATEGORIES_FILE))
    StepRun.objects.bulk_create(
        StepRun(run=run, name=name, position=position) for position, name in enumerate(step_names())
    )
    logger.info("run=%s created", run.pk)
    return run


def retry_run(run: PipelineRun) -> PipelineRun:
    if run.status != Status.FAILED:
        raise ValueError(f"only failed runs can be retried (run {run.pk} is {run.status})")
    return create_run(limit=run.limit, google_venues_file=run.google_venues_file,
                      food_categories_file=run.food_categories_file)


@transaction.atomic
def dispatch_waiting_runs(*, only: list[int] | None = None) -> list[int]:
    """Queues the first step of every WAITING run (or of the given ones). Returns the dispatched run ids."""
    runs = PipelineRun.objects.select_for_update(skip_locked=True).filter(status=Status.WAITING)
    if only is not None:
        runs = runs.filter(pk__in=only)
    dispatched = []
    for run in runs.order_by("created_at"):
        now = timezone.now()
        run.status, run.queued_at = Status.QUEUED, now
        run.save(update_fields=["status", "queued_at"])
        StepTransition(run.steps.order_by("position").first()).queue(now)
        dispatched.append(run.pk)
    logger.info("dispatched runs=%s", dispatched)
    return dispatched


def execute_step(step_id: int) -> None:
    transition = StepTransition.start(step_id)
    if transition is None:
        return
    step = transition.step
    try:
        outcome = get_handler(step.name)(step.run)
    except Exception as error:  # any failure of the step is recorded; the run stops there
        logger.exception("run=%s step=%s failed", step.run_id, step.name)
        transition.fail(f"{error.__class__.__name__}: {error}")
        return
    transition.succeed(outcome)


def fail_stalled_steps() -> int:
    """Fails steps stuck in QUEUED (the message never reached a worker) or RUNNING past the time limit (the
    worker died without recording anything). Returns how many were failed."""
    now = timezone.now()
    queued_limit = now - timedelta(seconds=settings.PIPELINE_QUEUED_TIMEOUT_SECONDS)
    running_limit = now - timedelta(seconds=settings.PIPELINE_STEP_TIME_LIMIT_SECONDS + STALLED_RUNNING_GRACE_SECONDS)
    stalled = {
        Status.QUEUED: ("queued_at__lt", queued_limit, "no worker picked it up in time"),
        Status.RUNNING: ("started_at__lt", running_limit, "still running past the time limit (worker lost?)"),
    }
    failed = 0
    for status, (lookup, limit, reason) in stalled.items():
        for step_id in StepRun.objects.filter(status=status, **{lookup: limit}).values_list("pk", flat=True):
            with transaction.atomic():
                step = StepRun.objects.select_for_update().select_related("run").get(pk=step_id)
                if step.status == status:  # not finished meanwhile
                    StepTransition(step).fail(f"StalledStep: {reason}")
                    failed += 1
    return failed
