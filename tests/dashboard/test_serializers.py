"""The contract of the dashboard API (apps/dashboard/serializers.py): every answer of DashboardService follows its
response serializer, field by field. frontend/src/schemas.ts mirrors these serializers by hand."""

import pytest

from apps.dashboard.dashboard_services import DashboardService
from apps.dashboard.serializers import (
    CategoryDetailSerializer,
    CategoryRowSerializer,
    DishRowSerializer,
    MatchGroupsSerializer,
    MenusSerializer,
    QualitySerializer,
    SummarySerializer,
    VenueRowSerializer,
)
from apps.venues.choices import MatchGroup

pytestmark = pytest.mark.django_db


@pytest.fixture
def service(pipeline):
    return DashboardService(pipeline)


def assert_follows(serializer_class, answer, many=False):
    """`answer` has exactly the fields of the contract, with their types (null only where allowed)."""
    serializer = serializer_class(data=answer, many=many)
    assert serializer.is_valid(), serializer.errors


def test_the_summary_follows_its_contract(service):
    assert_follows(SummarySerializer, {"run": service.run_info(), "matched": service.matched_restaurants(),
                                       "match_groups": service.match_groups()})


@pytest.mark.parametrize("group", MatchGroup.values)
def test_the_venue_rows_follow_their_contract(service, group):
    assert_follows(VenueRowSerializer, VenueRowSerializer(service.venues(group), many=True).data, many=True)


@pytest.mark.parametrize(("family", "level"), [("food", "parent"), ("food", "name"), ("drink", "parent")])
def test_the_top_categories_follow_their_contract(service, family, level):
    assert_follows(CategoryRowSerializer, service.top_categories(family=family, level=level), many=True)


@pytest.mark.parametrize(("level", "key"), [("parent", "pizza"), ("name", "burger")])
def test_a_category_detail_follows_its_contract(service, level, key):
    assert_follows(CategoryDetailSerializer, service.category_detail(level=level, key=key))


@pytest.mark.parametrize("group", [MatchGroup.ACCEPTED, MatchGroup.CONFIRMED])
def test_the_dish_rows_follow_their_contract(service, group):
    assert_follows(DishRowSerializer, DishRowSerializer(service.dishes(group), many=True).data, many=True)


def test_menus_and_quality_follow_their_contract(service):
    assert_follows(MenusSerializer, service.menus())
    assert_follows(QualitySerializer, service.quality())


def test_there_is_one_field_per_match_group():
    assert set(MatchGroupsSerializer().fields) == set(MatchGroup.values)


def test_a_field_outside_the_contract_is_an_error(service):
    serializer = MenusSerializer(data={**service.menus(), "extra": 1})

    assert not serializer.is_valid()
    assert set(serializer.errors) == {"extra"}


def test_a_missing_field_is_an_error(service):
    answer = service.menus()
    del answer["combo_share"]
    serializer = MenusSerializer(data=answer)

    assert not serializer.is_valid()
    assert set(serializer.errors) == {"combo_share"}


def test_a_venue_without_a_google_place_has_none(service):
    row = VenueRowSerializer(service.venues(MatchGroup.UNMATCHED).get()).data

    assert row["google"] is None


def test_prices_are_written_with_two_decimals(service):
    row = DishRowSerializer({"pk": 1, "venue__name": "Uno", "name": "Pizza", "section": "", "category__name": None,
                             "category__parent": None, "category__family": None, "confidence": 0.5,
                             "method": "pending", "price": 12.499}).data

    assert row["price"] == 12.5
