"""Output model: one venue as stored in just_eat_venues.json.

Field declaration order is part of the contract: it defines the key order of the JSON output and,
through it, the menu keys (a hash of the serialised menu).
"""

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _Out(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True)


class GeoPoint(_Out):
    type: str = "Point"
    coordinates: list[float]  # [longitude, latitude] (GeoJSON order)


class Address(_Out):
    city: str | None
    first_line: str | None
    postal_code: str | None
    location: GeoPoint


class Rating(_Out):
    count: int
    star_rating: int | float


class Option(_Out):
    name: str
    price: float | None = None
    id: str


class SubSelection(_Out):
    name: str
    multiple_selection: bool
    min_selection: int
    max_selection: int
    options: list[Option]


class MenuItem(_Out):
    id: str
    name: str
    description: str | None
    image: str | None
    image_filename: str
    price: int | float
    sub_selections: list[SubSelection]


class Section(_Out):
    id: str
    name: str
    description: str | None
    items: list[MenuItem]


class Menu(_Out):
    menu_group_id: str
    type: list[str]
    description: str | None
    sections: list[Section]


class TimeRange(_Out):
    from_local_time: str
    to_local_time: str


class DayTimes(_Out):
    day_of_week: str
    times: list[TimeRange]


class OpeningTimes(_Out):
    service_type: str
    times_per_day: list[DayTimes]


class Venue(_Out):
    name: str
    brand: str | None
    unique_name: str
    address: Address
    rating: Rating
    logo_url: str | None
    is_test_restaurant: bool
    cuisines: list[str]
    telephone: str | None = None
    ghost_store: bool | None = None
    menus: dict[str, Menu] = Field(default_factory=dict)
    description: str | None
    opening_times: list[OpeningTimes]
    store_front_type: str | None
    url: str
