import json
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from apps.menus.models import MenuItem
from apps.pipeline import run_services, tasks
from apps.pipeline.models import PipelineRun, Status
from apps.venues.models import MatchStatus, Source, StagedVenue, StagedVenueMatch, Venue, VenueMatch

scenarios("pipeline_run.feature")

pytestmark = pytest.mark.django_db


@pytest.fixture
def context():
    return {}


@given("Just Eat serves the curated venues")
def curated_venues(just_eat):
    """Tiflis, and a venue that no longer exists (see the just_eat fixture)."""


@given(parsers.parse("runs time out after {seconds} seconds"))
def run_timeout(monkeypatch, seconds):
    monkeypatch.setenv("CRAWLER_RUN_TIMEOUT_SECONDS", seconds)


@given("a run waiting to be processed")
def waiting_run(context):
    context["run"] = run_services.create_run()


@given("a run that already finished")
def finished_run(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        run = run_services.create_run()
        run_services.dispatch_waiting_runs(only=[run.pk])
    run.refresh_from_db()
    assert run.status == Status.SUCCEEDED, run.error_message


@given("a failed run")
def failed_run(context):
    run = run_services.create_run()
    PipelineRun.objects.filter(pk=run.pk).update(status=Status.FAILED)
    run.refresh_from_db()
    context["run"] = run


@when("the daily dispatcher runs")
def daily_dispatch(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        tasks.dispatch_waiting_runs.delay()  # the beat entry; tasks run inline in tests


@when("I retry it")
def retry(context):
    context["retry"] = run_services.retry_run(context["run"])


@then(parsers.parse('the run has succeeded with the steps "{names}"'))
def run_succeeded(context, names):
    run = context["run"]
    run.refresh_from_db()
    assert run.status == Status.SUCCEEDED, run.error_message
    assert [(step.name, step.status) for step in run.steps.all()] == [
        (name, Status.SUCCEEDED) for name in names.split(", ")]


@then(parsers.parse('the steps "{names}" never ran'))
def steps_never_ran(context, names):
    steps = context["run"].steps.filter(name__in=names.split(", "))
    assert {step.status for step in steps} == {Status.WAITING}


@given("the food categories file of new runs is broken")
def broken_taxonomy(settings, tmp_path):
    settings.FOOD_CATEGORIES_FILE = str(tmp_path / "missing.xlsx")


@then("the published venues, links and menu items are those of the finished run")
def published_untouched(context):
    finished = PipelineRun.objects.filter(published_at__isnull=False).get()
    assert finished.pk != context["run"].pk
    assert set(Venue.objects.values_list("last_run", flat=True)) == {finished.pk}
    assert set(VenueMatch.objects.values_list("run", flat=True)) == {finished.pk}
    assert set(MenuItem.objects.values_list("run", flat=True)) == {finished.pk}


@then("the failed run's staged data is kept for diagnosis")
def staged_kept(context):
    assert StagedVenue.objects.filter(run=context["run"], source=Source.JUST_EAT).count() == 1
    assert StagedVenueMatch.objects.filter(run=context["run"]).count() == 1


@then(parsers.parse('the Just Eat venue "{restaurant_id}" is linked to the Google place "{place_id}"'))
def linked(restaurant_id, place_id):
    match = VenueMatch.objects.get(just_eat__external_id=restaurant_id)
    assert (match.google.external_id, match.status) == (place_id, MatchStatus.ACCEPTED)


@then(parsers.parse('the run has failed with "{message}"'))
def run_failed(context, message):
    run = context["run"]
    run.refresh_from_db()
    assert run.status == Status.FAILED
    assert run.error_message.startswith(message), run.error_message  # file paths may follow


@then(parsers.parse('the step "{name}" reports {crawled:d} venue crawled and {failed:d} failed'))
def step_metrics(context, name, crawled, failed):
    step = context["run"].steps.get(name=name)
    assert (step.metrics["crawled"], step.metrics["failed"]) == (crawled, failed)
    assert step.output_dir


@then(parsers.parse('the database contains Just Eat venue "{restaurant_id}"'))
def venue_in_database(restaurant_id):
    assert list(Venue.objects.filter(source=Source.JUST_EAT).values_list("external_id", flat=True)) == [restaurant_id]


@then(parsers.parse('the menu item "{item}" of venue "{restaurant_id}" is in the category "{category}" of the '
                    'family "{family}"'))
def menu_item_category(item, restaurant_id, category, family):
    menu_item = MenuItem.objects.select_related("category").get(venue__external_id=restaurant_id, name=item)
    assert (menu_item.category.name, menu_item.category.family) == (category, family)


@then("the run folder contains the categorized menu items")
def menu_items_file(context):
    step = context["run"].steps.get(name="categorize_menu_items")
    assert step.output_dir == context["run"].steps.get(name="crawl_just_eat").output_dir
    rows = json.loads((Path(step.output_dir) / "menu_items.json").read_text(encoding="utf-8"))
    assert len(rows) == step.metrics["items"] == MenuItem.objects.count()


@then("the database contains no venues")
def no_venues():
    assert not Venue.objects.exists()


@then("a new run is waiting to be processed")
def new_waiting_run(context):
    assert context["retry"].pk != context["run"].pk
    assert context["retry"].status == Status.WAITING
