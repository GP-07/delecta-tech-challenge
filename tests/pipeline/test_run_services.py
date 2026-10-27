from datetime import timedelta

import pytest
from django.utils import timezone

from apps.pipeline import run_services
from apps.pipeline.models import PipelineRun, Status, StepRun
from tests.pipeline.conftest import BROKEN, EXTRACT, MATCH

pytestmark = pytest.mark.django_db


def _statuses(run):
    run.refresh_from_db()
    return run.status, [step.status for step in run.steps.all()]


# --- create ---------------------------------------------------------------------------------------------


def test_a_new_run_waits_with_all_its_steps_in_order():
    run = run_services.create_run(limit=10)

    assert run.status == Status.WAITING
    assert run.limit == 10
    assert [(step.name, step.position, step.status) for step in run.steps.all()] == [
        ("extract", 0, Status.WAITING),
        ("match", 1, Status.WAITING),
    ]


# --- dispatch -------------------------------------------------------------------------------------------


def test_dispatch_queues_the_first_step_of_every_waiting_run(django_capture_on_commit_callbacks):
    waiting = run_services.create_run()
    finished = run_services.create_run()
    PipelineRun.objects.filter(pk=finished.pk).update(status=Status.SUCCEEDED)

    with django_capture_on_commit_callbacks() as enqueued:
        dispatched = run_services.dispatch_waiting_runs()

    assert dispatched == [waiting.pk]
    assert _statuses(waiting) == (Status.QUEUED, [Status.QUEUED, Status.WAITING])
    assert waiting.queued_at is not None
    assert len(enqueued) == 1  # only sent to the queue once the transaction commits
    assert _statuses(finished) == (Status.SUCCEEDED, [Status.WAITING, Status.WAITING])


def test_a_run_is_never_dispatched_twice(django_capture_on_commit_callbacks):
    run_services.create_run()

    with django_capture_on_commit_callbacks() as enqueued:
        run_services.dispatch_waiting_runs()
        assert run_services.dispatch_waiting_runs() == []

    assert len(enqueued) == 1


def test_dispatch_can_be_limited_to_some_runs(django_capture_on_commit_callbacks):
    first, second = run_services.create_run(), run_services.create_run()

    with django_capture_on_commit_callbacks():
        assert run_services.dispatch_waiting_runs(only=[second.pk]) == [second.pk]

    assert _statuses(first)[0] == Status.WAITING


# --- execution ------------------------------------------------------------------------------------------


def test_each_successful_step_queues_the_next_until_the_run_succeeds(
        two_step_pipeline, django_capture_on_commit_callbacks):
    run = run_services.create_run()

    with django_capture_on_commit_callbacks(execute=True):
        run_services.dispatch_waiting_runs()

    assert two_step_pipeline == [("extract", run.pk), ("match", run.pk)]
    assert _statuses(run) == (Status.SUCCEEDED, [Status.SUCCEEDED, Status.SUCCEEDED])
    extract = run.steps.get(name="extract")
    assert extract.metrics == {"venues": 3}
    assert extract.output_dir == "/data/extract"
    assert extract.started_at <= extract.finished_at
    assert run.started_at <= run.finished_at
    assert run.error_message == ""


def test_a_failing_step_fails_the_run_with_its_message_and_stops_it(
        settings, two_step_pipeline, django_capture_on_commit_callbacks):
    settings.PIPELINE_STEPS = [EXTRACT, BROKEN, MATCH]
    run = run_services.create_run()

    with django_capture_on_commit_callbacks(execute=True):
        run_services.dispatch_waiting_runs()

    assert two_step_pipeline == [("extract", run.pk), ("broken", run.pk)]  # match never ran
    assert _statuses(run) == (Status.FAILED, [Status.SUCCEEDED, Status.FAILED, Status.WAITING])
    assert run.steps.get(name="broken").error_message == "ValueError: Just Eat answered 503"
    assert run.error_message == "broken: ValueError: Just Eat answered 503"
    assert run.finished_at is not None


def test_a_step_only_runs_from_the_queued_state(two_step_pipeline, django_capture_on_commit_callbacks):
    """A message delivered twice (e.g. the worker died before acknowledging it) must not run the step again."""
    run = run_services.create_run()
    with django_capture_on_commit_callbacks(execute=True):
        run_services.dispatch_waiting_runs()
    first_step = run.steps.get(position=0)

    run_services.execute_step(first_step.pk)  # redelivered after it already succeeded
    run_services.execute_step(999_999)  # deleted meanwhile

    assert two_step_pipeline == [("extract", run.pk), ("match", run.pk)]


# --- stalled steps --------------------------------------------------------------------------------------


def _stalled(status, age):
    run = run_services.create_run()
    step = run.steps.get(position=0)
    since = timezone.now() - age
    PipelineRun.objects.filter(pk=run.pk).update(status=status, queued_at=since, started_at=since)
    StepRun.objects.filter(pk=step.pk).update(status=status, queued_at=since, started_at=since)
    return run


def test_steps_that_never_reached_a_worker_are_failed(settings):
    settings.PIPELINE_QUEUED_TIMEOUT_SECONDS = 60
    lost = _stalled(Status.QUEUED, timedelta(minutes=2))
    recent = _stalled(Status.QUEUED, timedelta(seconds=10))

    assert run_services.fail_stalled_steps() == 1

    assert _statuses(lost) == (Status.FAILED, [Status.FAILED, Status.WAITING])
    assert "extract" in lost.error_message
    assert _statuses(recent)[0] == Status.QUEUED


def test_steps_running_past_the_time_limit_are_failed(settings):
    """The worker was killed (e.g. out of memory) and could not record the failure itself."""
    settings.PIPELINE_STEP_TIME_LIMIT_SECONDS = 60
    killed = _stalled(Status.RUNNING, timedelta(minutes=30))
    busy = _stalled(Status.RUNNING, timedelta(seconds=10))

    assert run_services.fail_stalled_steps() == 1

    assert _statuses(killed)[0] == Status.FAILED
    assert _statuses(busy)[0] == Status.RUNNING


# --- retry ----------------------------------------------------------------------------------------------


def test_a_failed_run_is_retried_as_a_new_waiting_run():
    failed = run_services.create_run(limit=5)
    PipelineRun.objects.filter(pk=failed.pk).update(status=Status.FAILED)
    failed.refresh_from_db()

    retry = run_services.retry_run(failed)

    assert retry.pk != failed.pk
    assert (retry.status, retry.limit) == (Status.WAITING, 5)


def test_only_failed_runs_can_be_retried():
    with pytest.raises(ValueError):
        run_services.retry_run(run_services.create_run())


def test_steps_use_the_configured_pipeline(settings):
    settings.PIPELINE_STEPS = [MATCH, EXTRACT]

    run = run_services.create_run()

    assert [step.name for step in run.steps.all()] == ["match", "extract"]
