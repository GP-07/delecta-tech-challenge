"""Corrections of people on the category of a menu item (from the admin)."""

from django.utils import timezone

from apps.menus.models import FoodCategory, MenuItem, Method


def correct(item: MenuItem, category: FoodCategory | None, user) -> None:
    """A person sets the category of an item: kept as MANUAL, no run changes it again."""
    item.category, item.method, item.confidence, item.evidence = category, Method.MANUAL, 1.0, ""
    item.reviewed_by, item.reviewed_at = user, timezone.now()
    item.save(update_fields=["category", "method", "confidence", "evidence", "reviewed_by", "reviewed_at",
                             "updated_at"])
