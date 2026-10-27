"""Raw Just Eat payloads, validated on the way in.

Only the fields the mapper needs are declared; everything else is ignored. Treating the payloads as
untrusted input means a schema change on Just Eat's side fails loudly here instead of producing a
silently broken venue downstream.
"""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel, to_pascal


class _Raw(BaseModel):
    model_config = ConfigDict(alias_generator=to_pascal, populate_by_name=True, extra="ignore", frozen=True)


# --- {slug}_es_manifest.json ---------------------------------------------------------------------


class Location(_Raw):
    address: str | None = None
    post_code: str | None = None
    city: str | None = None
    latitude: float
    longitude: float


class CuisineType(_Raw):
    seo_name: str


class TimeRange(_Raw):
    from_local_time: str
    to_local_time: str


class DayTimes(_Raw):
    day_of_week: str
    times: list[TimeRange] = Field(default_factory=list)


class OpeningTimes(_Raw):
    service_type: str
    times_per_day: list[DayTimes] = Field(default_factory=list)


class RestaurantInfo(_Raw):
    name: str
    seo_name: str
    description: str | None = None
    logo_url: str | None = None
    location: Location
    cuisine_types: list[CuisineType] = Field(default_factory=list)
    restaurant_opening_times: list[OpeningTimes] = Field(default_factory=list)
    store_front_type: str | None = None
    is_test_restaurant: bool = False


class Category(_Raw):
    id: str
    name: str
    description: str | None = None
    item_ids: list[str] = Field(default_factory=list)


class Menu(_Raw):
    menu_group_id: str
    description: str | None = None
    service_types: list[str] = Field(default_factory=list)
    categories: list[Category] = Field(default_factory=list)


class Manifest(_Raw):
    restaurant_id: str
    restaurant_info: RestaurantInfo
    menus: list[Menu] = Field(default_factory=list)
    items_url: str
    item_details_url: str


# --- {slug}_es_items.json ------------------------------------------------------------------------


class ImageSource(_Raw):
    path: str


class Variation(_Raw):
    id: str
    base_price: float
    modifier_groups_ids: list[str] | None = None


class Item(_Raw):
    id: str
    name: str
    description: str | None = None
    image_sources: list[ImageSource] | None = None
    variations: list[Variation] = Field(default_factory=list)


class ItemsPayload(_Raw):
    items: list[Item] = Field(default_factory=list)


# --- {slug}_es_itemDetails.json ------------------------------------------------------------------


class ModifierGroup(_Raw):
    id: str
    name: str
    min_choices: int
    max_choices: int
    modifiers: list[str] = Field(default_factory=list)


class Modifier(_Raw):
    name: str


class ModifierSet(_Raw):
    id: str
    modifier: Modifier


class ItemDetails(_Raw):
    modifier_groups: list[ModifierGroup] = Field(default_factory=list)
    modifier_sets: list[ModifierSet] = Field(default_factory=list)


# --- /restaurant/es/{id}/menu/dynamic ------------------------------------------------------------


class RestaurantRating(_Raw):
    rating_count: int = 0
    rating_average_stars: float = 0


class DynamicMenu(_Raw):
    restaurant_rating: RestaurantRating | None = None


# --- /discovery/es/restaurants/enriched/bypostcode/{postcode} (camelCase, unlike the rest) ---------


class _RawCamel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore", frozen=True)


class ListingCuisine(_RawCamel):
    unique_name: str


class ListedRestaurant(_RawCamel):
    id: str
    cuisines: list[ListingCuisine] = Field(default_factory=list)


class Listing(_RawCamel):
    restaurants: list[ListedRestaurant] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class VenueSource:
    """Everything Just Eat serves about one venue, before mapping."""

    manifest: Manifest
    items: ItemsPayload
    item_details: ItemDetails
    dynamic: DynamicMenu
    # Cuisines as shown in the area listing (includes tags like "lo-mas-top"); None if the venue is not listed.
    listing_cuisines: list[str] | None = None
