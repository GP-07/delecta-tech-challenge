"""The querysets the dashboard is built on: the published run, the venues of a run and of a match group."""

import pytest

from apps.menus.models import MenuItem
from apps.pipeline.models import PipelineRun, Status
from apps.venues.choices import MatchGroup
from apps.venues.models import Venue
from tests.dashboard.conftest import finished_run, venue

pytestmark = pytest.mark.django_db


def test_the_last_published_run_is_what_the_published_tables_hold(pipeline):
    PipelineRun.objects.create(status=Status.WAITING)
    PipelineRun.objects.create(status=Status.SUCCEEDED)  # finished, but never published

    assert PipelineRun.objects.last_published() == pipeline


def test_without_published_runs_there_is_none(db):
    PipelineRun.objects.create(status=Status.RUNNING)

    assert PipelineRun.objects.last_published() is None


def test_only_the_venues_the_run_crawled(pipeline):
    venue(finished_run(), "Crawled later")

    assert Venue.objects.crawled_by(pipeline).count() == 5


@pytest.mark.parametrize(("group", "names"), [
    (MatchGroup.ACCEPTED, ["Pizzeria Uno"]),
    (MatchGroup.CONFIRMED, ["Burger Dos"]),
    (MatchGroup.REVIEW, ["Sushi Tres"]),
    (MatchGroup.REJECTED, ["Kebab Cuatro"]),
    (MatchGroup.UNMATCHED, ["Bar Cinco"]),
])
def test_every_crawled_venue_is_in_exactly_one_match_group(pipeline, group, names):
    assert list(Venue.objects.crawled_by(pipeline).in_match_group(group).values_list("name", flat=True)) == names


def test_linked_venues_are_the_accepted_and_the_confirmed(pipeline):
    assert sorted(Venue.objects.crawled_by(pipeline).linked().values_list("name", flat=True)) == [
        "Burger Dos", "Pizzeria Uno"]


def test_menu_items_categorized_by_family_and_low_confidence(pipeline):
    items = MenuItem.objects.of_venues(Venue.objects.crawled_by(pipeline).linked())

    assert (items.count(), items.categorized().count(), items.categorized("drink").count()) == (8, 7, 2)
    assert list(items.low_confidence().values_list("name", flat=True)) == ["Pizza Barbacoa"]
