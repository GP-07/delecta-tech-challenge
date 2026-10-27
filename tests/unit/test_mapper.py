import hashlib
import json

import pytest

from libs.crawler.just_eat.mapper import IMAGE_TRANSFORMATIONS, VenueMapper, menu_key
from libs.crawler.just_eat.schemas import DynamicMenu, ItemDetails, ItemsPayload, Manifest, VenueSource
from tests.conftest import TIFLIS_URL


def test_maps_recorded_venue_to_the_expected_example(tiflis_source, tiflis_expected):
    venue = VenueMapper().map(tiflis_source, url=TIFLIS_URL, brand=None)

    assert venue.model_dump() == tiflis_expected


def test_output_keeps_the_key_order_of_the_example(tiflis_source, tiflis_expected):
    dumped = VenueMapper().map(tiflis_source, url=TIFLIS_URL, brand=None).model_dump()

    assert list(dumped) == list(tiflis_expected)
    assert json.dumps(dumped) == json.dumps(tiflis_expected)


def test_brand_comes_from_the_caller(tiflis_source):
    venue = VenueMapper().map(tiflis_source, url=TIFLIS_URL, brand="Some Brand")

    assert venue.brand == "Some Brand"


def test_menu_key_is_sha1_of_type_description_and_sections(tiflis_source):
    venue = VenueMapper().map(tiflis_source, url=TIFLIS_URL, brand=None)

    for key, menu in venue.menus.items():
        body = {"type": menu.type, "description": menu.description, "sections": menu.model_dump()["sections"]}
        assert key == hashlib.sha1(json.dumps(body).encode()).hexdigest()  # noqa: S324
        assert key == menu_key(menu)


# --- Rules inferred from just_eat_venues.json, on minimal synthetic payloads -------------------------


def _source(
    items: list[dict],
    details: dict | None = None,
    rating: dict | None = None,
    listing_cuisines: list[str] | None = None,
) -> VenueSource:
    manifest = {
        "RestaurantId": "1",
        "RestaurantInfo": {
            "Name": "Pizza Test",
            "SeoName": "pizza-test",
            "Description": "desc",
            "LogoUrl": "https://example.invalid/1.gif",
            "Location": {"Address": "C/ Mayor 1", "PostCode": "08001", "City": "Barcelona",
                         "Latitude": 41.1, "Longitude": 2.1},
            "CuisineTypes": [{"Id": "1", "Name": "Pizza", "SeoName": "pizza"}],
            "RestaurantOpeningTimes": [],
            "StoreFrontType": "Restaurant",
            "IsTestRestaurant": False,
        },
        "Menus": [{
            "MenuGroupId": "G1",
            "Description": "",
            "ServiceTypes": ["delivery"],
            "Categories": [
                {"Id": "c1", "Name": "Pizzas", "Description": "",
                 "ItemIds": [item["Id"] for item in items] + ["ghost"]},
                {"Id": "c2", "Name": "Parent category", "Description": None, "ItemIds": []},
            ],
        }],
        "ItemsUrl": "pizza-test_es_items.json",
        "ItemDetailsUrl": "pizza-test_es_itemDetails.json",
    }
    return VenueSource(
        manifest=Manifest.model_validate(manifest),
        items=ItemsPayload.model_validate({"Items": items}),
        item_details=ItemDetails.model_validate(details or {"ModifierGroups": [], "ModifierSets": []}),
        dynamic=DynamicMenu.model_validate({"RestaurantRating": rating}),
        listing_cuisines=listing_cuisines,
    )


DISH_PHOTO = "https://cdn.invalid/upload/c_fill,q_auto,{transformations}/v1/es/dishes/1/abc"


def _item(id_: str, prices: list[float], groups: list[list[str]] | None = None, image: str | None = DISH_PHOTO) -> dict:
    return {
        "Id": id_,
        "Name": f"Item {id_}",
        "Description": None,
        "ImageSources": [{"Path": image}] if image else [],
        "Variations": [
            {"Id": f"{id_}-{position}", "Name": f"size {position}", "BasePrice": price,
             "ModifierGroupsIds": (groups or [[]] * len(prices))[position]}
            for position, price in enumerate(prices)
        ],
    }


def _items_of(venue):
    (menu,) = venue.menus.values()
    return menu.sections[0].items


def test_multi_variation_item_keeps_price_and_modifiers_of_the_first_variation():
    details = {
        "ModifierGroups": [
            {"Id": "g-small", "Name": "Extras", "MinChoices": 0, "MaxChoices": 3, "Modifiers": ["1", "2"]},
            {"Id": "g-big", "Name": "Extras", "MinChoices": 0, "MaxChoices": 3, "Modifiers": ["3"]},
        ],
        "ModifierSets": [
            {"Id": "1", "Modifier": {"Name": "Queso", "AdditionPrice": 0.5}},
            {"Id": "2", "Modifier": {"Name": "Jamón", "AdditionPrice": 0.5}},
            {"Id": "3", "Modifier": {"Name": "Queso", "AdditionPrice": 1.0}},
        ],
    }
    source = _source([_item("a", [9.1, 12.1], groups=[["g-small"], ["g-big"]])], details)

    (item,) = _items_of(VenueMapper().map(source, url="u", brand=None))

    assert item.id == "a"
    assert item.price == 9.1
    assert [sub_selection.model_dump() for sub_selection in item.sub_selections] == [{
        "name": "Extras", "multipleSelection": True, "minSelection": 0, "maxSelection": 3,
        "options": [{"name": "Queso", "price": None, "id": "1"}, {"name": "Jamón", "price": None, "id": "2"}],
    }]


def test_single_choice_group_is_not_multiple_selection_and_option_prices_are_null():
    details = {
        "ModifierGroups": [{"Id": "g", "Name": "Elige 1", "MinChoices": 1, "MaxChoices": 1, "Modifiers": ["7"]}],
        "ModifierSets": [{"Id": "7", "Modifier": {"Name": "Ketchup", "AdditionPrice": 0.75}}],
    }
    source = _source([_item("a", [6.5], groups=[["g"]])], details)

    (item,) = _items_of(VenueMapper().map(source, url="u", brand=None))

    assert item.sub_selections[0].multiple_selection is False
    assert item.sub_selections[0].options[0].price is None


def test_whole_prices_and_ratings_are_written_as_integers():
    source = _source([_item("a", [11.0]), _item("b", [19.95])], rating={"RatingCount": 18, "RatingAverageStars": 4.0})

    venue = VenueMapper().map(source, url="u", brand=None)

    prices = [item.price for item in _items_of(venue)]
    assert prices == [11, 19.95]
    assert type(prices[0]) is int
    assert venue.rating.model_dump() == {"count": 18, "starRating": 4}
    assert type(venue.rating.star_rating) is int


def test_image_url_uses_fixed_transformations_and_filename_exists_even_without_image():
    source = _source([_item("a", [1.0]), _item("b", [1.0], image=None)])

    with_image, without_image = _items_of(VenueMapper().map(source, url="u", brand=None))

    assert with_image.image == f"https://cdn.invalid/upload/c_fill,q_auto,{IMAGE_TRANSFORMATIONS}/v1/es/dishes/1/abc"
    assert with_image.image_filename == "1_a.jpg"
    assert without_image.image is None
    assert without_image.image_filename == "1_b.jpg"


@pytest.mark.parametrize(
    "path",
    [
        "https://cdn.invalid/upload/{transformations}/t_jet_ai_watermark/v1/es/dishes/1/abc",  # AI generated
        "https://cdn.invalid/upload/{transformations}/v1/es/generic-products/water",  # stock
        "https://cdn.invalid/upload/{transformations}/v1/uk/databank-products/5000112592160/default",  # stock
        "http://cdn.invalid/upload/{transformations}/v1/Experiments/groceries/uk/Generic/beer",
    ],
)
def test_only_real_dish_photos_are_kept(path):
    (item,) = _items_of(VenueMapper().map(_source([_item("a", [1.0], image=path)]), url="u", brand=None))

    assert item.image is None
    assert item.image_filename == "1_a.jpg"


def test_cuisines_come_from_the_listing_when_the_venue_is_listed():
    source = _source([], listing_cuisines=["pizza", "lo-mas-top", "almuerzo"])

    assert VenueMapper().map(source, url="u", brand=None).cuisines == ["pizza", "lo-mas-top", "almuerzo"]


def test_cuisines_fall_back_to_the_manifest_when_the_venue_is_not_listed():
    assert VenueMapper().map(_source([]), url="u", brand=None).cuisines == ["pizza"]


def test_items_missing_from_the_catalogue_are_skipped_and_empty_sections_kept():
    source = _source([_item("a", [1.0])])

    venue = VenueMapper().map(source, url="u", brand=None)

    (menu,) = venue.menus.values()
    assert [len(section.items) for section in menu.sections] == [1, 0]
    assert menu.sections[1].description is None


def test_missing_rating_defaults_to_zero():
    venue = VenueMapper().map(_source([]), url="u", brand=None)

    assert venue.rating.model_dump() == {"count": 0, "starRating": 0}
