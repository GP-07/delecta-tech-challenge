from django.contrib import admin

from apps.menus import correction_services
from apps.menus.models import FoodCategory, MenuItem, Method
from libs.categorization.constants import LOW_CONFIDENCE


@admin.register(FoodCategory)
class FoodCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "parent", "family", "is_generic_or_other", "uidentifier"]
    list_filter = ["family", "parent", "is_generic_or_other"]
    search_fields = ["name", "parent", "uidentifier"]

    def has_add_permission(self, request):
        return False  # the taxonomy comes only from its file (FOOD_CATEGORIES_FILE)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class LowConfidenceFilter(admin.SimpleListFilter):
    title = "confianza"
    parameter_name = "confianza"

    def lookups(self, request, model_admin):
        return [("baja", f"Baja (< {LOW_CONFIDENCE})"), ("sin", "Sin categoría")]

    def queryset(self, request, queryset):
        if self.value() == "baja":
            return queryset.filter(category__isnull=False, confidence__lt=LOW_CONFIDENCE).exclude(method=Method.MANUAL)
        if self.value() == "sin":
            return queryset.filter(category__isnull=True)
        return queryset


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    """Items come from the pipeline; a person can only correct the category, which no run overwrites again."""

    list_display = ["name", "section", "venue_name", "category", "category_parent", "category_family", "confidence",
                    "method", "is_combo"]
    list_filter = [LowConfidenceFilter, "method", "category__family", "category__parent", "is_combo"]
    list_select_related = ["venue", "category"]
    search_fields = ["name", "section", "venue__name", "venue__external_id", "item_id"]
    autocomplete_fields = ["category"]
    fields = ["category", "venue", "item_id", "menu_ids", "section", "name", "description", "price", "confidence",
              "method", "is_combo", "evidence", "run", "classified_at", "reviewed_by", "reviewed_at"]
    readonly_fields = [field for field in fields if field != "category"]
    show_full_result_count = False

    @admin.display(description="Venue", ordering="venue__name")
    def venue_name(self, obj):
        return obj.venue.name

    @admin.display(description="Parent", ordering="category__parent")
    def category_parent(self, obj):
        return obj.category.parent if obj.category else None

    @admin.display(description="Family", ordering="category__family")
    def category_family(self, obj):
        return obj.category.family if obj.category else None

    def save_model(self, request, obj, form, change):
        correction_services.correct(obj, form.cleaned_data["category"], request.user)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
