import copy
import json
from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from apps.menus import correction_services
from apps.menus.models import FoodCategory, MenuItem, Method, StagedFoodCategory, StagedMenuItem
from apps.menus.publish_services import StalePublishError, publish_run
from apps.menus.staging_cleanup_services import purge_failed_runs
from apps.pipeline.models import PipelineRun, Status
from apps.pipeline.steps import StepNotDoneError
from apps.venues import review_services
from apps.venues.models import MatchStatus, Source, StagedVenue, StagedVenueMatch, Venue, VenueMatch
from tests.conftest import TIFLIS_ID, load_json
from tests.runs import categorized_run, matched_run, published_run

pytestmark = pytest.mark.django_db

TIFLIS_ITEMS = 89
TIFLIS_PLACE = "ChIJqTJI7ESjpBIR7jRF8cSRyDI"


@pytest.fixture
def google_without_tiflis(settings, tmp_path):
    records = [record for record in load_json(Path(settings.GOOGLE_VENUES_FILE))
               if record["googlePlaceId"] != TIFLIS_PLACE]
    path = tmp_path / "google_without_tiflis.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


def published_state():
    """Everything the admin and the dashboard show."""
    return (
        sorted(Venue.objects.values_list("source", "external_id", "name", "last_run_id")),
        sorted(VenueMatch.objects.values_list("just_eat__external_id", "google__external_id", "status", "run_id")),
        FoodCategory.objects.count(),
        sorted(MenuItem.objects.values_list("item_id", "name", "category__name", "method", "run_id")),
    )


def test_publishing_makes_the_whole_run_visible_and_deletes_its_staged_rows(tiflis_expected):
    run = categorized_run({TIFLIS_ID: tiflis_expected})

    metrics = publish_run(run)

    assert (metrics["google"], metrics["just_eat"], metrics["matches"], metrics["items"]) == (3, 1, 1, TIFLIS_ITEMS)
    assert Venue.objects.get(source=Source.JUST_EAT).last_run == run
    match = VenueMatch.objects.get()
    assert (match.google.external_id, match.status, match.run) == (TIFLIS_PLACE, MatchStatus.ACCEPTED, run)
    salad = MenuItem.objects.select_related("category").get(name="Ensalada Georgiana")
    assert (salad.category.name, salad.method, salad.run) == ("salads", Method.NAME, run)
    assert FoodCategory.objects.count() == 101
    run.refresh_from_db()
    assert run.published_at is not None
    for staged in (StagedVenue, StagedVenueMatch, StagedMenuItem, StagedFoodCategory):
        assert not staged.objects.exists()


def test_a_run_that_fails_before_publishing_leaves_the_published_data_untouched(tiflis_expected):
    published_run({TIFLIS_ID: tiflis_expected})
    before = published_state()
    renamed = {**tiflis_expected, "name": "Tiflis (renamed)"}

    categorized_run({TIFLIS_ID: renamed})  # every step but publish_run: e.g. the worker died while publishing

    assert published_state() == before


def test_publishing_needs_every_previous_step_of_the_run(tiflis_expected):
    run = matched_run({TIFLIS_ID: tiflis_expected})  # categorize_menu_items never succeeded

    with pytest.raises(StepNotDoneError, match="categorize_menu_items"):
        publish_run(run)

    assert not Venue.objects.exists()


def test_a_run_never_publishes_over_a_newer_one(tiflis_expected):
    older = categorized_run({TIFLIS_ID: {**tiflis_expected, "name": "Older"}})
    published_run({TIFLIS_ID: tiflis_expected})
    before = published_state()

    with pytest.raises(StalePublishError):
        publish_run(older)

    assert published_state() == before


def test_a_link_rejected_while_the_run_was_going_is_not_published_again(tiflis_expected):
    published_run({TIFLIS_ID: tiflis_expected})
    run = categorized_run({TIFLIS_ID: tiflis_expected})  # proposes the link again
    review_services.reject(VenueMatch.objects.get(), user=None)  # meanwhile, a person rejects it

    metrics = publish_run(run)

    assert metrics["matches_skipped"] == 1
    assert list(VenueMatch.objects.values_list("status", flat=True)) == [MatchStatus.REJECTED]
    assert not MenuItem.objects.exists()  # the venue is no longer linked: its items go


def test_a_link_confirmed_while_the_run_was_going_stays_confirmed(tiflis_expected):
    published_run({TIFLIS_ID: tiflis_expected})
    run = categorized_run({TIFLIS_ID: tiflis_expected})
    review_services.confirm(VenueMatch.objects.get(), user=None)

    publish_run(run)

    assert list(VenueMatch.objects.values_list("status", flat=True)) == [MatchStatus.CONFIRMED]
    assert MenuItem.objects.count() == TIFLIS_ITEMS


def test_a_category_corrected_while_the_run_was_going_is_kept(tiflis_expected):
    published_run({TIFLIS_ID: tiflis_expected})
    run = categorized_run({TIFLIS_ID: tiflis_expected})
    pork = FoodCategory.objects.get(name="pork")
    correction_services.correct(MenuItem.objects.get(name="Odjakhuri"), pork, user=None)

    publish_run(run)

    odjakhuri = MenuItem.objects.select_related("category").get(name="Odjakhuri")
    assert (odjakhuri.category.name, odjakhuri.method, odjakhuri.confidence) == ("pork", Method.MANUAL, 1.0)


def test_items_no_longer_on_the_menu_are_removed(tiflis_expected):
    published_run({TIFLIS_ID: tiflis_expected})
    venue = copy.deepcopy(tiflis_expected)
    for menu in venue["menus"].values():
        for section in menu["sections"]:
            section["items"] = [item for item in section["items"] if item["name"] != "Patatas Fritas"]

    metrics = publish_run(categorized_run({TIFLIS_ID: venue}))

    assert metrics["items_removed"] == 1
    assert not MenuItem.objects.filter(name="Patatas Fritas").exists()


def test_venues_the_run_did_not_crawl_are_kept(tiflis_expected):
    published_run({TIFLIS_ID: tiflis_expected})

    published_run({})  # e.g. Just Eat failed for every venue

    assert Venue.objects.filter(source=Source.JUST_EAT).count() == 1
    assert MenuItem.objects.count() == TIFLIS_ITEMS


def test_a_google_place_no_longer_in_the_file_is_removed_with_its_automatic_link(
        tiflis_expected, google_without_tiflis):
    published_run({TIFLIS_ID: tiflis_expected})

    published_run({TIFLIS_ID: tiflis_expected}, google_file=google_without_tiflis)

    assert not Venue.objects.filter(external_id=TIFLIS_PLACE).exists()
    assert not VenueMatch.objects.filter(google__external_id=TIFLIS_PLACE).exists()


def test_a_confirmed_link_whose_google_place_left_the_file_goes_back_to_a_person(
        tiflis_expected, google_without_tiflis, settings):
    published_run({TIFLIS_ID: tiflis_expected})
    review_services.confirm(VenueMatch.objects.get(), user=None)

    metrics = publish_run(categorized_run({TIFLIS_ID: tiflis_expected}, google_file=google_without_tiflis))

    match = VenueMatch.objects.get()
    assert (match.google.external_id, match.status, match.google_missing) == (
        TIFLIS_PLACE, MatchStatus.REVIEW, True)
    assert metrics["google_missing"] == 1
    assert not MenuItem.objects.exists()  # in review: not categorized

    published_run({TIFLIS_ID: tiflis_expected}, google_file=settings.GOOGLE_VENUES_FILE)  # the place is back

    match.refresh_from_db()
    assert (match.status, match.google_missing) == (MatchStatus.CONFIRMED, False)
    assert MenuItem.objects.count() == TIFLIS_ITEMS


def test_staged_rows_of_failed_runs_are_deleted_after_the_retention(tiflis_expected, settings):
    settings.PIPELINE_STAGING_RETENTION_DAYS = 7
    old, recent = (categorized_run({TIFLIS_ID: tiflis_expected}) for _ in range(2))
    PipelineRun.objects.filter(pk=old.pk).update(status=Status.FAILED,
                                                 finished_at=timezone.now() - timedelta(days=8))
    PipelineRun.objects.filter(pk=recent.pk).update(status=Status.FAILED, finished_at=timezone.now())

    assert purge_failed_runs() == 1

    assert set(StagedVenue.objects.values_list("run", flat=True)) == {recent.pk}
    assert not StagedMenuItem.objects.filter(run=old).exists()
