from django.db import models

from apps.pipeline.choices import Status
from apps.pipeline.querysets import PipelineRunQuerySet

__all__ = ["PipelineRun", "Status", "StepRun"]


class PipelineRun(models.Model):
    """One execution of the whole pipeline. Created WAITING; the daily dispatcher picks it up.

    WAITING -> QUEUED -> RUNNING -> SUCCEEDED | FAILED. Never resumed: a failed run is retried as a new run.
    """

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.WAITING, db_index=True)
    limit = models.PositiveIntegerField(null=True, blank=True, help_text="Solo los primeros N venues (pruebas).")
    google_venues_file = models.CharField(max_length=500, blank=True,
                                          help_text="Archivo de Google que carga esta corrida (GOOGLE_VENUES_FILE).")
    google_venues_sha256 = models.CharField(max_length=64, blank=True,
                                            help_text="SHA-256 del archivo de Google, calculado al cargarlo.")
    food_categories_file = models.CharField(
        max_length=500, blank=True, help_text="Taxonomía de platos que usa esta corrida (FOOD_CATEGORIES_FILE).")
    food_categories_sha256 = models.CharField(max_length=64, blank=True,
                                              help_text="SHA-256 de la taxonomía, calculado al leerla.")
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    queued_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True,
                                        help_text="Cuándo sus resultados pasaron a las tablas que se ven.")

    objects = PipelineRunQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "corrida"

    def __str__(self) -> str:
        return f"Corrida #{self.pk} ({self.get_status_display()})"


class StepRun(models.Model):
    """One step of a run (e.g. crawl_just_eat). The steps of a run execute in `position` order."""

    run = models.ForeignKey(PipelineRun, on_delete=models.CASCADE, related_name="steps")
    name = models.CharField(max_length=64)
    position = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.WAITING, db_index=True)
    error_message = models.TextField(blank=True)
    output_dir = models.CharField(max_length=500, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    queued_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["run", "position"]
        constraints = [
            models.UniqueConstraint(fields=["run", "position"], name="unique_step_position_per_run"),
            models.UniqueConstraint(fields=["run", "name"], name="unique_step_name_per_run"),
        ]
        verbose_name = "paso"

    def __str__(self) -> str:
        return f"{self.name} ({self.get_status_display()})"
