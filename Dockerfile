# Dashboard frontend (React): built here; the final image only has the static files, not Node.
FROM node:24-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
# Exact versions from the lockfile, no install scripts, and no known high vulnerabilities.
RUN npm ci --ignore-scripts && npm audit --audit-level=high
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Embedding model for the menu categorization: downloaded here, at a pinned revision with checked SHA-256, so
# the pipeline never downloads anything while it runs (HF_HUB_OFFLINE). Before copying the code, and with only
# the download script, so a code change does not download it again.
RUN pip install huggingface_hub==1.33.0  # the version fastembed resolves to (pip install -e . keeps it)
COPY src/libs/categorization/download_model.py ./src/libs/categorization/
RUN python src/libs/categorization/download_model.py /app/data/downloads/embedding_model
ENV CATEGORIZATION_EMBEDDING_MODEL_PATH=/app/data/downloads/embedding_model HF_HUB_OFFLINE=1

COPY pyproject.toml ./
COPY src ./src
RUN pip install -e .

COPY manage.py ./
COPY --from=frontend /build/src/apps/dashboard/static/dashboard ./src/apps/dashboard/static/dashboard
# Static files for whitenoise (production settings); nothing here connects to the database or the broker.
RUN DJANGO_SETTINGS_MODULE=config.settings.production DJANGO_SECRET_KEY=collectstatic DJANGO_ALLOWED_HOSTS=build \
    DATABASE_URL=postgres://build@localhost/build CELERY_BROKER_URL=redis://localhost \
    python manage.py collectstatic --noinput
# Never run as root: the app only needs to write its outputs.
RUN useradd --create-home --uid 1000 app && mkdir -p /app/output && chown app /app/output
USER app
