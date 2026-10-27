"""manage.py start_pipeline: creates a WAITING run, picked up by the next daily dispatch.

    manage.py start_pipeline              # waits for the daily dispatch (PIPELINE_DISPATCH_HOUR)
    manage.py start_pipeline --now        # sends it to the queue right away
    manage.py start_pipeline --limit 10   # only the first 10 venues (tests)
    manage.py start_pipeline --google-venues-file /data/google_venues.json   # default: GOOGLE_VENUES_FILE
    manage.py start_pipeline --food-categories-file /data/food_categories.xlsx   # default: FOOD_CATEGORIES_FILE
"""

from django.core.management.base import BaseCommand

from apps.pipeline import run_services


class Command(BaseCommand):
    help = "Creates a pipeline run in WAITING state (optionally dispatching it right away)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, help="Only process the first N venues")
        parser.add_argument("--now", action="store_true", help="Send it to the queue now instead of waiting")
        parser.add_argument("--google-venues-file", help="Google venues JSON to load (default: GOOGLE_VENUES_FILE)")
        parser.add_argument("--food-categories-file",
                            help="Food taxonomy (xlsx) to classify menu items (default: FOOD_CATEGORIES_FILE)")

    def handle(self, *args, limit, now, google_venues_file, food_categories_file, **options):
        run = run_services.create_run(limit=limit, google_venues_file=google_venues_file,
                                  food_categories_file=food_categories_file)
        if now:
            run_services.dispatch_waiting_runs(only=[run.pk])
        run.refresh_from_db()
        self.stdout.write(f"run {run.pk}: {run.status}")
