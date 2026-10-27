from django.db import models

from apps.pipeline.choices import Status


class PipelineRunQuerySet(models.QuerySet):
    def published(self) -> "PipelineRunQuerySet":
        """Runs whose results reached the published tables."""
        return self.filter(status=Status.SUCCEEDED, published_at__isnull=False)

    def last_published(self):
        """What the published tables hold now: the last run published, or None."""
        return self.published().order_by("-published_at", "-pk").first()

    def started_after(self, run) -> "PipelineRunQuerySet":
        """Runs created after `run` that already left the queue (going, finished or failed)."""
        return self.filter(pk__gt=run.pk).exclude(status=Status.WAITING)
