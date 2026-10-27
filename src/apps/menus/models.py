from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.menus.querysets import MenuItemQuerySet
from apps.venues.models import Source


class FoodCategory(models.Model):
    """A category of the food taxonomy (food_categories.xlsx), as published by the last run."""

    uidentifier = models.CharField(max_length=40, unique=True)
    family = models.CharField(max_length=16, db_index=True)
    name = models.CharField(max_length=100, unique=True)
    parent = models.CharField(max_length=100, db_index=True)
    is_generic_or_other = models.BooleanField()

    class Meta:
        ordering = ["family", "parent", "name"]
        verbose_name = "categoría"

    def __str__(self) -> str:
        return f"{self.name} ({self.parent} · {self.family})"


class Method(models.TextChoices):
    """What decided the category of an item (see categorization.classifier)."""

    NAME = "name", "Nombre del plato"
    SECTION = "section", "Sección del menú"
    DESCRIPTION = "description", "Descripción"
    EMBEDDING = "embedding", "Platos parecidos (embeddings)"
    NON_FOOD = "non_food", "No es comida ni bebida"
    UNKNOWN = "unknown", "Sin categoría"
    PENDING = "pending", "Pendiente de clasificar"
    MANUAL = "manual", "Corregido a mano"


class StagedFoodCategory(models.Model):
    """The taxonomy a run read (its food_categories_file), before publish_run copies it to FoodCategory."""

    run = models.ForeignKey("pipeline.PipelineRun", on_delete=models.CASCADE, related_name="+")
    uidentifier = models.CharField(max_length=40)
    family = models.CharField(max_length=16)
    name = models.CharField(max_length=100)
    parent = models.CharField(max_length=100)
    is_generic_or_other = models.BooleanField()

    class Meta:
        verbose_name = "categoría de una corrida"
        constraints = [
            models.UniqueConstraint(fields=["run", "uidentifier"], name="unique_staged_category_per_run"),
            models.UniqueConstraint(fields=["run", "name"], name="unique_staged_category_name_per_run"),
        ]


class MenuItemData(models.Model):
    """The fields of a menu item, shared by MenuItem and StagedMenuItem."""

    item_id = models.CharField(max_length=64, help_text="Id del ítem en Just Eat.")
    menu_ids = ArrayField(models.CharField(max_length=64), default=list, blank=True,
                          help_text="Menús del venue en los que aparece.")
    section = models.CharField(max_length=255, blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    confidence = models.FloatField(default=0)
    method = models.CharField(max_length=16, choices=Method.choices, default=Method.PENDING, db_index=True)
    is_combo = models.BooleanField(default=False, help_text="Menú o combo: clasificado por su plato principal.")
    evidence = models.CharField(max_length=255, blank=True, help_text="Palabra o plato parecido que lo decidió.")
    classified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


class MenuItem(MenuItemData):
    """A dish or drink of the menus of a Just Eat venue linked to its Google place (accepted or confirmed match).

    Published: only publish_run writes it (see venues.Venue). One row per item of the venue, even when it is in
    several of its menus (delivery, collection...). Its text is the venue's current one; its category is
    recomputed by the runs, except after a person corrected it.
    """

    venue = models.ForeignKey("venues.Venue", on_delete=models.CASCADE, related_name="menu_items",
                              limit_choices_to={"source": Source.JUST_EAT})
    category = models.ForeignKey(FoodCategory, null=True, blank=True, on_delete=models.PROTECT,
                                 related_name="items")
    run = models.ForeignKey("pipeline.PipelineRun", null=True, blank=True, on_delete=models.SET_NULL,
                            related_name="+", help_text="Última corrida que lo escribió.")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = MenuItemQuerySet.as_manager()

    class Meta:
        ordering = ["venue", "section", "name"]
        verbose_name = "ítem de menú"
        verbose_name_plural = "ítems de menú"
        constraints = [
            models.UniqueConstraint(fields=["venue", "item_id"], name="unique_menu_item_per_venue"),
        ]
        indexes = [models.Index(fields=["confidence"])]

    def __str__(self) -> str:
        return self.name


class StagedMenuItem(MenuItemData):
    """An item as a run's categorize_menu_items step left it, before publish_run copies it to MenuItem."""

    run = models.ForeignKey("pipeline.PipelineRun", on_delete=models.CASCADE, related_name="+")
    venue = models.ForeignKey("venues.StagedVenue", on_delete=models.CASCADE, related_name="menu_items")
    category = models.ForeignKey(StagedFoodCategory, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="items")

    class Meta:
        verbose_name = "ítem de una corrida"
        constraints = [
            models.UniqueConstraint(fields=["venue", "item_id"], name="unique_staged_item_per_venue"),
        ]
