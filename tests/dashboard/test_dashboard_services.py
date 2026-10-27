"""One test (or a few) per chart of the dashboard, against the hand-made result of conftest.py."""

import pytest

from apps.dashboard.dashboard_services import CategoryNotFoundError, DashboardService
from apps.dashboard.serializers import VenueRowSerializer
from apps.pipeline.models import PipelineRun, Status
from apps.venues.choices import MatchGroup
from tests.dashboard.conftest import finished_run, venue

pytestmark = pytest.mark.django_db


@pytest.fixture
def service(pipeline):
    return DashboardService(pipeline)


# --- main view --------------------------------------------------------------------------------------------


def test_run_info(service, pipeline):
    info = service.run_info()

    assert (info["id"], info["newer_run"], [step["name"] for step in info["steps"]]) == (
        pipeline.pk, None, ["crawl_just_eat"])


@pytest.mark.parametrize("status", [Status.RUNNING, Status.FAILED])
def test_a_later_run_that_started_is_reported(service, status):
    PipelineRun.objects.create(status=Status.FAILED)
    newer = PipelineRun.objects.create(status=status)

    assert service.run_info()["newer_run"] == {"id": newer.pk, "status": status}


def test_matched_restaurants(service):
    assert service.matched_restaurants() == {"matched": 2, "crawled": 5}


def test_venues_crawled_by_another_run_are_not_counted(service):
    venue(finished_run(), "Crawled later")

    assert service.matched_restaurants()["crawled"] == 5


def test_match_groups_add_up_to_the_crawled_venues(service):
    assert service.match_groups() == {"accepted": 1, "confirmed": 1, "review": 1, "rejected": 1, "unmatched": 1}


@pytest.mark.parametrize(("group", "names"), [
    (MatchGroup.ACCEPTED, ["Pizzeria Uno"]),
    (MatchGroup.REVIEW, ["Sushi Tres"]),
    (MatchGroup.UNMATCHED, ["Bar Cinco"]),
])
def test_venues_of_a_match_group(service, group, names):
    assert [venue.name for venue in service.venues(group)] == names


def test_a_venue_row_shows_its_google_place(service):
    row = VenueRowSerializer(service.venues(MatchGroup.ACCEPTED).get()).data

    assert row["google"] == {"name": "Uno (Google)", "address": "", "star_rating": 4.0, "rating_count": None,
                             "status": "ACCEPTED", "score": 0.95, "distance_m": 10.0, "reason": "test"}


def test_top_food_offerings_by_number_of_restaurants(service):
    assert service.top_categories(family="food", level="parent") == [
        {"key": "pizza", "family": "food", "items": 4, "venues": 2, "venues_share": 1.0, "median_price": 11.0},
        {"key": "fast food", "family": "food", "items": 1, "venues": 1, "venues_share": 0.5, "median_price": 9.0},
    ]


def test_top_categories_by_exact_category_and_number_of_items(service):
    top = service.top_categories(family="food", level="name", order="items", top=2)

    assert [(category["key"], category["items"]) for category in top] == [("pizza other", 3), ("burger", 1)]


def test_drinks_have_their_own_ranking(service):
    drinks = service.top_categories(family="drink")

    assert [(category["key"], category["median_price"]) for category in drinks] == [("soft drinks", 1.75)]


def test_category_detail(service):
    detail = service.category_detail(level="parent", key="pizza")

    assert (detail["key"], detail["family"], detail["items"], detail["venues"]) == ("pizza", "food", 4, 2)
    assert [(subcategory["key"], subcategory["items"], subcategory["venues"])
            for subcategory in detail["subcategories"]] == [("pizza other", 3, 2), ("pizza margherita", 1, 1)]
    assert [(venue["name"], venue["items"]) for venue in detail["top_venues"]] == [
        ("Pizzeria Uno", 3), ("Burger Dos", 1)]
    assert {dish["name"] for dish in detail["top_dishes"]} == {
        "margherita", "diavola", "menú pizza + bebida", "pizza barbacoa"}


def test_an_unknown_category_is_an_error(service):
    with pytest.raises(CategoryNotFoundError):
        service.category_detail(level="parent", key="pasta")


# --- "more detail" ----------------------------------------------------------------------------------------


def test_dishes_of_a_matched_group(service):
    dishes = list(service.dishes(MatchGroup.CONFIRMED))

    assert [dish["name"] for dish in dishes] == ["Agua", "Bolsa", "Classic Burger", "Pizza Barbacoa"]
    assert {key: dishes[0][key] for key in ("venue__name", "category__name", "category__family")} == {
        "venue__name": "Burger Dos", "category__name": "water", "category__family": "drink"}


def test_menu_size_drinks_and_combos(service):
    assert service.menus() == {"venues": 2, "median_items": 4.0, "venues_with_drinks": 1.0, "combo_share": 0.125}


def test_quality_of_the_categorization(service):
    quality = service.quality()

    assert quality["items"] == {"total": 8, "categorized": 7, "low_confidence": 1, "pending": 0}
    assert quality["methods"] == [{"method": "name", "label": "Nombre del plato", "items": 5},
                                  {"method": "embedding", "label": "Platos parecidos (embeddings)", "items": 1},
                                  {"method": "non_food", "label": "No es comida ni bebida", "items": 1},
                                  {"method": "section", "label": "Sección del menú", "items": 1}]
    assert [bucket["items"] for bucket in quality["confidence"]] == [0, 1, 2, 4]
