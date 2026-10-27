"""Every change of status of a step, and of its run with it. Each one happens inside a transaction.

    StepTransition.start(step_id)   QUEUED -> RUNNING (and the run RUNNING); None if the step is not QUEUED
    transition.queue(now)           -> QUEUED, its message sent to the queue once the transaction commits
    transition.succeed(outcome)     RUNNING -> SUCCEEDED; queues the next step, or finishes the run
    transition.fail(message)        -> FAILED, and the run FAILED with the step's error

A step only starts from QUEUED: a message sent twice, or delivered again after a worker crash, does nothing.
"""

import functools
import logging

from django.db import transaction
from django.utils import timezone

from apps.pipeline.constants import MAX_ERROR_LENGTH
from apps.pipeline.models import Status, StepRun
from apps.pipeline.steps import StepOutcome

logger = logging.getLogger(__name__)


def send_to_queue(step_id: int) -> None:
    from apps.pipeline.tasks import run_step  # the tasks module imports the services

    run_step.delay(step_id)


class StepTransition:
    """The transitions of one step (a StepRun loaded with its run)."""

    def __init__(self, step: StepRun) -> None:
        self.step = step
        self.run = step.run

    @classmethod
    @transaction.atomic
    def start(cls, step_id: int) -> "StepTransition | None":
        step = StepRun.objects.select_for_update().select_related("run").filter(pk=step_id).first()
        if step is None or step.status != Status.QUEUED:
            logger.warning("step=%s is %s, not queued: ignored", step_id, step and step.status)
            return None
        transition = cls(step)
        now = timezone.now()
        step.status, step.started_at = Status.RUNNING, now
        step.save(update_fields=["status", "started_at"])
        if transition.run.status != Status.RUNNING:
            transition.run.status, transition.run.started_at = Status.RUNNING, transition.run.started_at or now
            transition.run.save(update_fields=["status", "started_at"])
        logger.info("run=%s step=%s started", transition.run.pk, step.name)
        return transition

    def queue(self, now) -> None:
        """Must run inside the caller's transaction: the message is only sent once it commits."""
        self.step.status, self.step.queued_at = Status.QUEUED, now
        self.step.save(update_fields=["status", "queued_at"])
        transaction.on_commit(functools.partial(send_to_queue, self.step.pk))

    @transaction.atomic
    def succeed(self, outcome: StepOutcome) -> None:
        now = timezone.now()
        step = self.step
        step.status, step.finished_at = Status.SUCCEEDED, now
        step.metrics, step.output_dir = outcome.metrics, outcome.output_dir
        step.save(update_fields=["status", "finished_at", "metrics", "output_dir"])
        logger.info("run=%s step=%s succeeded metrics=%s", self.run.pk, step.name, outcome.metrics)

        following = self.run.steps.filter(position__gt=step.position).order_by("position").first()
        if following is not None:
            StepTransition(following).queue(now)
            return
        self.run.status, self.run.finished_at = Status.SUCCEEDED, now
        self.run.save(update_fields=["status", "finished_at"])
        logger.info("run=%s succeeded", self.run.pk)

    @transaction.atomic
    def fail(self, message: str) -> None:
        now = timezone.now()
        message = message[:MAX_ERROR_LENGTH]
        step = self.step
        step.status, step.finished_at, step.error_message = Status.FAILED, now, message
        step.save(update_fields=["status", "finished_at", "error_message"])
        self.run.status, self.run.finished_at = Status.FAILED, now
        self.run.error_message = f"{step.name}: {message}"[:MAX_ERROR_LENGTH]
        self.run.save(update_fields=["status", "finished_at", "error_message"])
