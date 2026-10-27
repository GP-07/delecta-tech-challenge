"""manage.py crawl_just_eat: crawls the Just Eat venues right now into files, without going through the queue.

    manage.py crawl_just_eat              # all of just_eat_urls.json: output/<UTC start>/just_eat_venues.json
    manage.py crawl_just_eat --limit 10   # only the first 10

It never writes the database: only a pipeline run publishes venues (start_pipeline), so the admin and the dashboard
always show the whole result of one run.

Exit codes: 0 all crawled, 1 some venues failed, 2 the run timed out and must be reprocessed.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from libs.crawler.processor import CrawlJob, CrawlProcessor, CrawlTimeoutError


class Command(BaseCommand):
    help = "Crawls the Just Eat venues of just_eat_urls.json into JSON files (never into the database)."

    def add_arguments(self, parser):
        parser.add_argument("-o", "--output-dir", type=Path,
                            help="Base folder; each run creates its own timestamped sub-folder "
                                 "(default: PIPELINE_OUTPUT_DIR)")
        parser.add_argument("--limit", type=int, help="Only crawl the first N venues")
        parser.add_argument("--brands", type=Path, help="Custom {uniqueName: brand} JSON (default: bundled)")

    def handle(self, *args, output_dir, limit, brands, **options):
        job = CrawlJob(output_dir=output_dir or settings.PIPELINE_OUTPUT_DIR, limit=limit, brands_file=brands)
        processor = CrawlProcessor(job)
        try:
            result = processor.run_sync()
        except CrawlTimeoutError as error:
            raise CommandError(f"{error}; partial results in {processor.run_dir}", returncode=2) from error

        self.stdout.write(f"{result.crawled}/{result.requested} venues crawled into {result.output_path}")
        if not result.ok:
            raise CommandError(f"{result.failed} venues failed, see {result.failures_path}", returncode=1)
