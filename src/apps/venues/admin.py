from django.contrib import admin, messages

from apps.venues import review_services
from apps.venues.models import MatchStatus, Venue, VenueMatch


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ["name", "brand", "source", "external_id", "postal_code", "star_rating", "rating_count",
                    "store_front_type", "updated_at"]
    list_filter = ["source", "store_front_type", "brand"]
    search_fields = ["name", "brand", "unique_name", "external_id", "postal_code"]
    readonly_fields = [field.name for field in Venue._meta.fields]
    show_full_result_count = False

    def has_add_permission(self, request):
        return False  # venues come only from the pipeline

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(VenueMatch)
class VenueMatchAdmin(admin.ModelAdmin):
    list_display = ["just_eat_name", "just_eat_address", "google_name", "google_address", "status", "score",
                    "distance_m", "same_address", "google_missing", "reason"]
    list_filter = ["status", "google_missing", "reason", "same_address"]
    list_select_related = ["just_eat", "google"]
    search_fields = ["just_eat__name", "google__name", "just_eat__external_id", "google__external_id"]
    readonly_fields = [field.name for field in VenueMatch._meta.fields]
    actions = ["confirm", "reject"]

    @admin.display(description="Just Eat", ordering="just_eat__name")
    def just_eat_name(self, obj):
        return obj.just_eat.name

    @admin.display(description="Dirección Just Eat")
    def just_eat_address(self, obj):
        return obj.just_eat.address

    @admin.display(description="Google", ordering="google__name")
    def google_name(self, obj):
        return obj.google.name

    @admin.display(description="Dirección Google")
    def google_address(self, obj):
        return obj.google.address

    @admin.action(description="Confirmar vínculo (es el mismo local)")
    def confirm(self, request, queryset):
        for match in queryset.exclude(status=MatchStatus.CONFIRMED):
            review_services.confirm(match, request.user)
        self.message_user(request, "Vínculos confirmados.", messages.SUCCESS)

    @admin.action(description="Rechazar vínculo (no es el mismo local)")
    def reject(self, request, queryset):
        for match in queryset.exclude(status=MatchStatus.REJECTED):
            review_services.reject(match, request.user)
        self.message_user(request, "Vínculos rechazados.", messages.SUCCESS)

    def has_add_permission(self, request):
        return False  # links come from the pipeline; people only confirm or reject them

    def has_change_permission(self, request, obj=None):
        return False
