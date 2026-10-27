"""Maps raw Just Eat payloads to the output Venue.

The rules below were inferred from just_eat_venues.json and are pinned by tests:
- one menu per Just Eat menu group (i.e. per service type), keyed by ``menu_key``;
- an item with several variations (sizes) keeps the price and modifiers of its FIRST variation;
- option prices are never stored (always null);
- whole numbers are written as ints (11, not 11.0), which also affects the menu keys;
- images are referenced by URL only, with fixed Cloudinary transformations, and only when they are real
  photos of the venue's dishes (no AI-generated or stock images);
- cuisines are the ones shown in the area listing (they include tags such as "lo-mas-top"), falling back
  to the venue's own cuisines when it is not listed.
"""

import hashlib
import json
import logging

from libs.crawler import domain
from libs.crawler.constants import AI_GENERATED_MARK, DISH_PHOTO, IMAGE_TRANSFORMATIONS
from libs.crawler.just_eat import schemas

logger = logging.getLogger(__name__)



def menu_key(menu: domain.Menu) -> str:
    """sha1 of the serialised menu content (everything but its group id).

    Identical menus in different venues share a key. The serialisation must match json.dumps defaults
    and the output key order, so it is built from the dumped model.
    """
    body = menu.model_dump(exclude={"menu_group_id"})
    return hashlib.sha1(json.dumps(body).encode()).hexdigest()  # noqa: S324 - content key, not security


def _number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


class VenueMapper:
    def map(self, source: schemas.VenueSource, *, url: str, brand: str | None) -> domain.Venue:
        manifest = source.manifest
        info = manifest.restaurant_info
        menus = _MenuBuilder(source).build()
        return domain.Venue(
            name=info.name,
            brand=brand,
            unique_name=info.seo_name,
            address=domain.Address(
                city=info.location.city,
                first_line=info.location.address,
                postal_code=info.location.post_code,
                location=domain.GeoPoint(coordinates=[info.location.longitude, info.location.latitude]),
            ),
            rating=self._rating(source.dynamic),
            logo_url=info.logo_url,
            is_test_restaurant=info.is_test_restaurant,
            cuisines=(
                source.listing_cuisines
                if source.listing_cuisines is not None
                else [cuisine.seo_name for cuisine in info.cuisine_types]
            ),
            menus={menu_key(menu): menu for menu in menus},
            description=info.description,
            opening_times=[
                domain.OpeningTimes(
                    service_type=opening.service_type,
                    times_per_day=[
                        domain.DayTimes(
                            day_of_week=day.day_of_week,
                            times=[
                                domain.TimeRange(from_local_time=time_range.from_local_time,
                                                 to_local_time=time_range.to_local_time)
                                for time_range in day.times
                            ],
                        )
                        for day in opening.times_per_day
                    ],
                )
                for opening in info.restaurant_opening_times
            ],
            store_front_type=info.store_front_type,
            url=url,
        )

    @staticmethod
    def _rating(dynamic: schemas.DynamicMenu) -> domain.Rating:
        rating = dynamic.restaurant_rating or schemas.RestaurantRating()
        return domain.Rating(count=rating.rating_count, star_rating=_number(rating.rating_average_stars))


class _MenuBuilder:
    """Builds the menus of one venue, resolving item and modifier references."""

    def __init__(self, source: schemas.VenueSource) -> None:
        self._restaurant_id = source.manifest.restaurant_id
        self._menus = source.manifest.menus
        self._items = {item.id: item for item in source.items.items}
        self._groups = {group.id: group for group in source.item_details.modifier_groups}
        self._modifiers = {mod_set.id: mod_set.modifier for mod_set in source.item_details.modifier_sets}

    def build(self) -> list[domain.Menu]:
        return [
            domain.Menu(
                menu_group_id=menu.menu_group_id,
                type=menu.service_types,
                description=menu.description,
                sections=[self._section(category) for category in menu.categories],
            )
            for menu in self._menus
        ]

    def _section(self, category: schemas.Category) -> domain.Section:
        items = []
        for item_id in category.item_ids:
            item = self._items.get(item_id)
            if item is None or not item.variations:
                logger.warning("restaurant=%s item=%s referenced but not in catalogue, skipped",
                               self._restaurant_id, item_id)
                continue
            items.append(self._item(item))
        return domain.Section(id=category.id, name=category.name, description=category.description, items=items)

    def _item(self, item: schemas.Item) -> domain.MenuItem:
        first_variation = item.variations[0]
        return domain.MenuItem(
            id=item.id,
            name=item.name,
            description=item.description,
            image=self._image_url(item),
            image_filename=f"{self._restaurant_id}_{item.id}.jpg",
            price=_number(first_variation.base_price),
            sub_selections=[
                self._sub_selection(self._groups[group_id])
                for group_id in first_variation.modifier_groups_ids or []
                if group_id in self._groups
            ],
        )

    @staticmethod
    def _image_url(item: schemas.Item) -> str | None:
        if not item.image_sources:
            return None
        path = item.image_sources[0].path
        if not DISH_PHOTO.search(path) or AI_GENERATED_MARK in path:
            return None
        return path.replace("{transformations}", IMAGE_TRANSFORMATIONS)

    def _sub_selection(self, group: schemas.ModifierGroup) -> domain.SubSelection:
        return domain.SubSelection(
            name=group.name,
            multiple_selection=group.max_choices > 1,
            min_selection=group.min_choices,
            max_selection=group.max_choices,
            options=[
                domain.Option(name=self._modifiers[modifier_id].name, id=modifier_id)
                for modifier_id in group.modifiers
                if modifier_id in self._modifiers
            ],
        )
