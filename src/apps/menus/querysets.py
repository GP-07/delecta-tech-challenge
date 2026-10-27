"""Querysets of the published menu items:

    MenuItem.objects.of_venues(Venue.objects.crawled_by(run).linked()).categorized(family="food")
"""

from django.db import models

from libs.categorization.constants import LOW_CONFIDENCE


class MenuItemQuerySet(models.QuerySet):
    def of_venues(self, venues) -> "MenuItemQuerySet":
        return self.filter(venue__in=venues)

    def categorized(self, family: str | None = None) -> "MenuItemQuerySet":
        """With a category (of that family: "food" or "drink", when given)."""
        items = self.filter(category__isnull=False)
        return items.filter(category__family=family) if family else items

    def low_confidence(self) -> "MenuItemQuerySet":
        """Categorized with a confidence below LOW_CONFIDENCE: a guess worth reviewing."""
        return self.categorized().filter(confidence__lt=LOW_CONFIDENCE)
