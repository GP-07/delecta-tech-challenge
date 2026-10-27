"""The contract of the dashboard API: what each endpoint accepts and what it answers.

Query parameters: only the listed values are accepted; anything else is a 400.

Responses: one serializer per structure, and each one has its counterpart, with the same name and fields, in
frontend/src/schemas.ts (`VenueRowSerializer` <-> `VenueRow`). Changing a field here means changing it there too.

    endpoint                answer
    summary/                SummarySerializer
    venues/                 Page of VenueRowSerializer
    categories/             list of CategoryRowSerializer
    categories/detail/      CategoryDetailSerializer
    dishes/                 Page of DishRowSerializer
    menus/                  MenusSerializer
    quality/                QualitySerializer

A serializer shapes an answer but does not check it when it writes it. The response serializers are strict when
they read (ResponseSerializer: a field the contract does not have is an error), so the tests check every answer of
DashboardService against its serializer with `is_valid()`.
"""

from rest_framework import serializers

from apps.dashboard.constants import DISH_GROUPS, FAMILIES, LEVELS, MATCH_GROUPS, ORDERS
from apps.menus.models import Method
from apps.pipeline.choices import Status
from apps.venues.choices import MatchStatus

# --- query parameters ------------------------------------------------------------------------------------------


class CategoriesParams(serializers.Serializer):
    family = serializers.ChoiceField(FAMILIES, default="food")
    level = serializers.ChoiceField(LEVELS, default="parent")
    order = serializers.ChoiceField(ORDERS, default="venues")
    top = serializers.IntegerField(min_value=1, max_value=50, default=10)


class CategoryDetailParams(serializers.Serializer):
    level = serializers.ChoiceField(LEVELS)
    key = serializers.CharField(max_length=100)


class VenuesParams(serializers.Serializer):
    group = serializers.ChoiceField(MATCH_GROUPS)


class DishesParams(serializers.Serializer):
    group = serializers.ChoiceField(DISH_GROUPS)


# --- shared by the responses -----------------------------------------------------------------------------------


class RoundedFloatField(serializers.FloatField):
    """A float written with at most `digits` decimals: 0.953 for a score, 12.5 for a price."""

    def __init__(self, *, digits: int, **kwargs) -> None:
        self.digits = digits
        super().__init__(**kwargs)

    def to_representation(self, value) -> float:
        return round(super().to_representation(value), self.digits)


class ResponseSerializer(serializers.Serializer):
    """A response of the API. When it reads an answer (the tests), a field the contract does not have is an error,
    so an answer can be neither shorter nor longer than its contract."""

    def to_internal_value(self, data):
        unknown = sorted(set(data) - set(self.fields))
        if unknown:
            raise serializers.ValidationError({field: "No es parte del contrato." for field in unknown})
        return super().to_internal_value(data)


def text() -> serializers.CharField:
    """A text field that may be empty (an address, a section)."""
    return serializers.CharField(allow_blank=True)


def price() -> RoundedFloatField:
    return RoundedFloatField(digits=2, allow_null=True)


# --- summary/ --------------------------------------------------------------------------------------------------


class NewerRunSerializer(ResponseSerializer):
    id = serializers.IntegerField()
    status = serializers.ChoiceField(Status.values)


class StepSerializer(ResponseSerializer):
    name = serializers.CharField()
    status = serializers.ChoiceField(Status.values)
    seconds = serializers.IntegerField(allow_null=True)


class RunInfoSerializer(ResponseSerializer):
    id = serializers.IntegerField()
    finished_at = serializers.DateTimeField()
    seconds = serializers.IntegerField(allow_null=True)
    newer_run = NewerRunSerializer(allow_null=True)
    steps = StepSerializer(many=True)


class MatchedRestaurantsSerializer(ResponseSerializer):
    matched = serializers.IntegerField()
    crawled = serializers.IntegerField()


class MatchGroupsSerializer(ResponseSerializer):
    """Crawled venues per match group (MatchGroup): one field per group (a test checks none is missing)."""

    accepted = serializers.IntegerField()
    confirmed = serializers.IntegerField()
    review = serializers.IntegerField()
    rejected = serializers.IntegerField()
    unmatched = serializers.IntegerField()


class SummarySerializer(ResponseSerializer):
    run = RunInfoSerializer()
    matched = MatchedRestaurantsSerializer()
    match_groups = MatchGroupsSerializer()


# --- venues/ ---------------------------------------------------------------------------------------------------


class GoogleLinkSerializer(ResponseSerializer):
    """The Google place of a venue: from its VenueMatch."""

    name = serializers.CharField(source="google.name")
    address = serializers.CharField(source="google.address", allow_blank=True)
    star_rating = serializers.FloatField(source="google.star_rating", allow_null=True)
    rating_count = serializers.IntegerField(source="google.rating_count", allow_null=True)
    status = serializers.ChoiceField(MatchStatus.values)
    score = RoundedFloatField(digits=3)
    distance_m = RoundedFloatField(digits=1)
    reason = text()


class ShownGoogleLinkSerializer(GoogleLinkSerializer):
    """The Google place shown with a venue: its active link, or the last rejected one (DashboardService.venues
    prefetches them newest first); None for a venue without any."""

    def get_attribute(self, instance):
        return next(iter(instance.google_matches.all()), None)


class VenueRowSerializer(ResponseSerializer):
    """A venue of a match-group list (from a Venue)."""

    id = serializers.CharField(source="external_id")
    name = serializers.CharField()
    city = text()
    address = text()
    url = text()
    cuisines = serializers.ListField(child=serializers.CharField())
    star_rating = serializers.FloatField(allow_null=True)
    rating_count = serializers.IntegerField(allow_null=True)
    google = ShownGoogleLinkSerializer(allow_null=True)


# --- categories/ and categories/detail/ ------------------------------------------------------------------------


class CategoryRowSerializer(ResponseSerializer):
    key = serializers.CharField()
    family = serializers.ChoiceField(FAMILIES)
    items = serializers.IntegerField()
    venues = serializers.IntegerField()
    venues_share = serializers.FloatField()
    median_price = price()


class SubcategorySerializer(ResponseSerializer):
    key = serializers.CharField()
    items = serializers.IntegerField()
    venues = serializers.IntegerField()
    median_price = price()


class TopDishSerializer(ResponseSerializer):
    name = serializers.CharField()
    items = serializers.IntegerField()
    median_price = price()


class TopVenueSerializer(ResponseSerializer):
    name = serializers.CharField()
    items = serializers.IntegerField()


class CategoryDetailSerializer(ResponseSerializer):
    key = serializers.CharField()
    level = serializers.ChoiceField(LEVELS)
    family = serializers.ChoiceField(FAMILIES)
    items = serializers.IntegerField()
    venues = serializers.IntegerField()
    median_price = price()
    subcategories = SubcategorySerializer(many=True)
    top_dishes = TopDishSerializer(many=True)
    top_venues = TopVenueSerializer(many=True)


# --- dishes/ ---------------------------------------------------------------------------------------------------


class DishRowSerializer(ResponseSerializer):
    """A dish of the dish list (from DashboardService.dishes, a MenuItem `.values()`)."""

    id = serializers.IntegerField(source="pk")
    venue = serializers.CharField(source="venue__name")
    name = serializers.CharField()
    section = text()
    category = serializers.CharField(source="category__name", allow_null=True)
    parent = serializers.CharField(source="category__parent", allow_null=True)
    family = serializers.ChoiceField(FAMILIES, source="category__family", allow_null=True)
    confidence = serializers.FloatField()
    method = serializers.ChoiceField(Method.values)
    price = price()


# --- menus/ and quality/ ---------------------------------------------------------------------------------------


class MenusSerializer(ResponseSerializer):
    venues = serializers.IntegerField()
    median_items = serializers.FloatField(allow_null=True)
    venues_with_drinks = serializers.FloatField()
    combo_share = serializers.FloatField()


class QualityItemsSerializer(ResponseSerializer):
    total = serializers.IntegerField()
    categorized = serializers.IntegerField()
    low_confidence = serializers.IntegerField()
    pending = serializers.IntegerField()


class MethodCountSerializer(ResponseSerializer):
    method = serializers.ChoiceField(Method.values)
    label = serializers.CharField()
    items = serializers.IntegerField()


class ConfidenceBucketSerializer(ResponseSerializer):
    bucket = serializers.CharField()
    items = serializers.IntegerField()


class QualitySerializer(ResponseSerializer):
    items = QualityItemsSerializer()
    methods = MethodCountSerializer(many=True)
    confidence = ConfidenceBucketSerializer(many=True)
