"""Settings shared by every environment. Secrets and hosts come only from environment variables (or a local,
git-ignored .env file); nothing sensitive lives in the repository.
"""

from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parents[3]  # project root (next to manage.py)

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")  # never overrides variables already set (e.g. by docker compose)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "apps.pipeline",
    "apps.venues",
    "apps.menus",
    "apps.dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.dashboard.middleware.ContentSecurityPolicyMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=60)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es"
TIME_ZONE = "Europe/Madrid"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Shared by the web processes (failed logins are counted here): Redis in docker compose and production.
CACHES = {"default": env.cache("CACHE_URL", default="locmemcache://")}

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"
LOGIN_MAX_FAILURES = env.int("LOGIN_MAX_FAILURES", default=5)
LOGIN_LOCKOUT_SECONDS = env.int("LOGIN_LOCKOUT_SECONDS", default=15 * 60)
SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE", default=8 * 3600)
SESSION_COOKIE_SAMESITE = "Lax"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {"httpx": {"level": "WARNING"}},
}

# --- pipeline -------------------------------------------------------------------------------------------

# Steps of every run, in order: when one succeeds, the next one is queued.
PIPELINE_STEPS = [
    ("crawl_just_eat", "apps.venues.steps.crawl_just_eat"),
    ("load_google_venues", "apps.venues.steps.load_google_venues"),
    ("match_venues", "apps.venues.steps.match_venues"),
    ("categorize_menu_items", "apps.menus.steps.categorize_menu_items"),
    ("publish_run", "apps.menus.steps.publish_run"),  # the only step that writes what the admin and dashboard show
]
# Staged rows of failed runs are kept this long for diagnosis, then deleted (PIPELINE_STAGING_CLEANUP, hourly).
PIPELINE_STAGING_RETENTION_DAYS = env.int("PIPELINE_STAGING_RETENTION_DAYS", default=7)
PIPELINE_STAGING_CLEANUP = "apps.menus.staging_cleanup_services.purge_failed_runs"

# Base folder of the crawl outputs; every run creates its own timestamped sub-folder in it.
PIPELINE_OUTPUT_DIR = Path(env("PIPELINE_OUTPUT_DIR", default=str(BASE_DIR / "output")))
# A step that does not finish within this time is killed by Celery and marked as failed.
PIPELINE_STEP_TIME_LIMIT_SECONDS = env.int("PIPELINE_STEP_TIME_LIMIT_SECONDS", default=2 * 3600)
# Google venues file (google_venues.json) every new run loads; recorded in the run when it is created.
GOOGLE_VENUES_FILE = env("GOOGLE_VENUES_FILE", default="")
GOOGLE_VENUES_MAX_BYTES = env.int("GOOGLE_VENUES_MAX_BYTES", default=300 * 1024 * 1024)
# Food taxonomy (food_categories.xlsx) every new run classifies menu items with; recorded in the run.
FOOD_CATEGORIES_FILE = env("FOOD_CATEGORIES_FILE", default="")
# At most this many menu items are classified per run; the rest wait for the next runs. 0 (default): every item of
# the run, so each published run is fully classified (~122,000 items take about 5 minutes).
CATEGORIZATION_MAX_ITEMS_PER_RUN = env.int("CATEGORIZATION_MAX_ITEMS_PER_RUN", default=0)
# Local embedding model (fastembed, ONNX) for the items no rule decides. Prepared when the image is built
# (src/libs/categorization/download_model.py); empty: rules only.
CATEGORIZATION_EMBEDDING_MODEL = env("CATEGORIZATION_EMBEDDING_MODEL",
                                     default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
CATEGORIZATION_EMBEDDING_MODEL_PATH = env("CATEGORIZATION_EMBEDDING_MODEL_PATH", default="")
# A step still queued after this long never reached a worker (e.g. the message was lost): it is marked as failed.
PIPELINE_QUEUED_TIMEOUT_SECONDS = env.int("PIPELINE_QUEUED_TIMEOUT_SECONDS", default=3600)

# --- celery ---------------------------------------------------------------------------------------------

CELERY_BROKER_URL = env("CELERY_BROKER_URL")
CELERY_TASK_SERIALIZER = "json"  # never pickle: a message must not be able to run code in the worker
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_IGNORE_RESULT = True  # the outcome lives in the database, not in a result backend
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True  # a task lost with its worker is delivered again (tasks are idempotent)
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # long tasks: do not reserve work another worker could take
CELERY_TASK_TIME_LIMIT = PIPELINE_STEP_TIME_LIMIT_SECONDS + 300
CELERY_TASK_SOFT_TIME_LIMIT = PIPELINE_STEP_TIME_LIMIT_SECONDS
# Redis re-delivers unacknowledged messages after this long; must exceed the longest task.
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": CELERY_TASK_TIME_LIMIT + 600}
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# Every step in a fresh worker process: the memory of a large step goes back to the system when it ends.
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1

CELERY_BEAT_SCHEDULE = {
    "dispatch-waiting-runs": {
        "task": "pipeline.dispatch_waiting_runs",
        "schedule": crontab(hour=env.int("PIPELINE_DISPATCH_HOUR", default=6), minute=0),
    },
    "fail-stalled-steps": {
        "task": "pipeline.fail_stalled_steps",
        "schedule": crontab(minute="*/15"),
    },
    "purge-staged-runs": {
        "task": "pipeline.purge_staged_runs",
        "schedule": crontab(minute=30),
    },
}

# --- dashboard ------------------------------------------------------------------------------------------

# Read-only JSON API: session login only (the page and the API are the same site), JSON only, nothing is ever
# parsed from a request body, and every user has a request budget.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["apps.dashboard.permissions.CanViewDashboard"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"user": env("DASHBOARD_THROTTLE_RATE", default="300/min")},
    "UNAUTHENTICATED_USER": None,
}
# The page: the React build (frontend/, `npm run build` writes it into the app's static folder).
DASHBOARD_INDEX_FILE = env("DASHBOARD_INDEX_FILE",
                           default=str(BASE_DIR / "src" / "apps" / "dashboard" / "static" / "dashboard" / "index.html"))
DASHBOARD_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
