import io

import pytest
from django.core.management import call_command

from apps.pipeline.models import PipelineRun, Status

pytestmark = pytest.mark.django_db


def _start(*args):
    out = io.StringIO()
    call_command("start_pipeline", *args, stdout=out)
    return out.getvalue()


def test_start_pipeline_leaves_the_run_waiting_for_the_daily_dispatch():
    assert _start("--limit", "10").strip().endswith("WAITING")

    run = PipelineRun.objects.get()
    assert (run.status, run.limit) == (Status.WAITING, 10)


def test_start_pipeline_now_sends_it_to_the_queue(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks() as enqueued:
        _start("--now")

    assert PipelineRun.objects.get().status == Status.QUEUED
    assert len(enqueued) == 1


def test_the_google_file_is_fixed_when_the_run_starts(settings):
    settings.GOOGLE_VENUES_FILE = "/data/google_venues.json"

    _start()
    _start("--google-venues-file", "/data/google_venues_2026.json")

    assert list(PipelineRun.objects.order_by("pk").values_list("google_venues_file", flat=True)) == [
        "/data/google_venues.json", "/data/google_venues_2026.json"]
