"""Reading the menus of a venue, as crawled ({menu hash: menu} of just_eat_venues.json)."""

from decimal import Decimal, InvalidOperation

from apps.menus.constants import CENT, MAX_ITEM_ID_LENGTH, MAX_TEXT_LENGTH


def menu_items(menus: dict | None) -> dict[str, dict]:
    """{item id: fields} of the menus of a venue; an item in several menus (delivery, collection) once."""
    items: dict[str, dict] = {}
    for menu_id, menu in (menus or {}).items():
        for section in menu.get("sections") or []:
            for item in section.get("items") or []:
                row = items.setdefault(str(item["id"])[:MAX_ITEM_ID_LENGTH], {
                    "section": (section.get("name") or "")[:MAX_TEXT_LENGTH],
                    "name": (item.get("name") or "")[:MAX_TEXT_LENGTH],
                    "description": item.get("description") or "",
                    "price": parse_price(item.get("price")),
                    "menu_ids": [],
                })
                row["menu_ids"].append(str(menu_id)[:MAX_ITEM_ID_LENGTH])
    return items


def parse_price(value) -> Decimal | None:
    """12.5 -> Decimal('12.50'); None for a missing or invalid price."""
    try:
        return Decimal(str(value)).quantize(CENT) if value is not None else None
    except InvalidOperation:
        return None
