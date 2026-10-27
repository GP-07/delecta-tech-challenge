from django.contrib import admin, messages

from apps.pipeline import run_services
from apps.pipeline.models import PipelineRun, Status, StepRun


class StepRunInline(admin.TabularInline):
    model = StepRun
    extra = 0
    can_delete = False
    fields = readonly_fields = ["position", "name", "status", "queued_at", "started_at", "finished_at",
                                "metrics", "output_dir", "error_message"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display = ["id", "status", "limit", "created_at", "started_at", "finished_at", "error_message"]
    list_filter = ["status"]
    # Input files come from the settings, never from a form: a server path is not for users to choose.
    readonly_fields = ["status", "google_venues_file", "google_venues_sha256", "food_categories_file",
                       "food_categories_sha256", "error_message", "created_at", "queued_at", "started_at",
                       "finished_at"]
    inlines = [StepRunInline]
    actions = ["retry"]

    def get_readonly_fields(self, request, obj=None):
        # The limit can only be chosen when creating a run; afterwards everything is managed by the pipeline.
        return [*self.readonly_fields, "limit"] if obj else self.readonly_fields

    def save_model(self, request, obj, form, change):
        if change:
            return super().save_model(request, obj, form, change)
        obj.pk = run_services.create_run(limit=obj.limit).pk  # with its steps, like start_pipeline
        obj.refresh_from_db()

    @admin.action(description="Reprocesar como corrida nueva (solo fallidas)")
    def retry(self, request, queryset):
        failed = list(queryset.filter(status=Status.FAILED))
        for run in failed:
            run_services.retry_run(run)
        self.message_user(request, f"{len(failed)} corridas nuevas en espera.", messages.SUCCESS)
