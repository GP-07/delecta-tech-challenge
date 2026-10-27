"""Development on a laptop or with docker compose. Never use in production."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "insecure-local-development-key")
os.environ.setdefault("DJANGO_DEBUG", "true")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")

from config.settings.base import *  # noqa: E402, F403
