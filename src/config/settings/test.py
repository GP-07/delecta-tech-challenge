"""Test runs: Celery tasks run inline, so no broker or worker is needed."""

from config.settings.local import *  # noqa: F403

DEBUG = False
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast; test users only
GOOGLE_VENUES_FILE = str(BASE_DIR / "tests" / "fixtures" / "google" / "google_venues.json")  # noqa: F405
FOOD_CATEGORIES_FILE = str(BASE_DIR / "tests" / "fixtures" / "categorization" / "food_categories.xlsx")  # noqa: F405
CATEGORIZATION_EMBEDDING_MODEL_PATH = ""  # tests never load the model; they use a fake embedder where needed
