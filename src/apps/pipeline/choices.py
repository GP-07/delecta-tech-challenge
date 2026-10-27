from django.db import models


class Status(models.TextChoices):
    WAITING = "WAITING", "En espera"
    QUEUED = "QUEUED", "Encolado"
    RUNNING = "RUNNING", "En curso"
    SUCCEEDED = "SUCCEEDED", "Terminado"
    FAILED = "FAILED", "Fallido"
