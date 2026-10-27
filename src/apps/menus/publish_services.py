"""publish_run: the last step of a run. Copies everything the run staged into the published tables, in a single
transaction, then deletes the run's staged rows.

Until this step, nothing a run does is visible: if any step fails, the admin and the dashboard keep showing the
last published run, whole. Runs publish one at a time (a database lock), and a run never publishes over a newer
one already published (StalePublishError): its data would be older.

    publish_run(run)       venues and links (apps.venues.publish_services), then taxonomy and menu items (MenuPublisher)
"""

import logging
from dataclasses import asdict, dataclass

from django.db import connection, transaction
from django.utils import timezone

from apps.menus.constants import (
    BATCH_SIZE,
    FIELDS_KEPT_BY_PEOPLE,
    ITEM_FIELDS,
    PUBLISH_LOCK_ID,
    STEPS_BEFORE_PUBLISHING,
)
from apps.menus.models import FoodCategory, MenuItem, Method, StagedFoodCategory, StagedMenuItem
from apps.menus.staging_cleanup_services import purge_run
from apps.pipeline.models import PipelineRun
from apps.pipeline.steps import require_succeeded
from apps.venues.choices import LINKED_MATCH_STATUSES
from apps.venues.models import Source, StagedVenue, Venue
from apps.venues.publish_services import publish_venues

logger = logging.getLogger(__name__)


class StalePublishError(Exception):
    """A newer run was published already: publishing this one would bring back older data."""


@dataclass(frozen=True)
class MenusPublished:
    categories: int
    categories_removed: int
    items: int
    items_removed: int


def publish_run(run: PipelineRun) -> dict:
    require_succeeded(run, *STEPS_BEFORE_PUBLISHING)
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [PUBLISH_LOCK_ID])
        newer = PipelineRun.objects.filter(pk__gt=run.pk, published_at__isnull=False).order_by("-pk").first()
        if newer is not None:
            raise StalePublishError(f"run {newer.pk} was published after this run started: nothing published")
        venues = publish_venues(run)
        menus = MenuPublisher(run).publish()
        run.published_at = timezone.now()
        run.save(update_fields=["published_at"])
        purge_run(run)
    metrics = {**asdict(venues), **asdict(menus)}
    logger.info("run=%s published: %s", run.pk, metrics)
    return metrics


def upsert_items(rows: list[MenuItem]) -> None:
    MenuItem.objects.bulk_create(rows, update_conflicts=True, unique_fields=["venue", "item_id"],
                                 update_fields=[*ITEM_FIELDS, "category", "run", "updated_at"])


class MenuPublisher:
    """Publishes one run's taxonomy and the menu items of its linked venues (after its venues were published)."""

    def __init__(self, run: PipelineRun) -> None:
        self.run = run
        self.linked_venues = Venue.objects.filter(
            source=Source.JUST_EAT, google_matches__status__in=LINKED_MATCH_STATUSES,
            external_id__in=StagedVenue.objects.filter(run=run, source=Source.JUST_EAT).values("external_id"))

    def publish(self) -> MenusPublished:
        categories, categories_removed = self._publish_taxonomy()
        published = self._publish_items()
        items_removed = self._remove_items_not_published(published)
        return MenusPublished(categories=categories, categories_removed=categories_removed, items=len(published),
                              items_removed=items_removed)

    def _publish_taxonomy(self) -> tuple[int, int]:
        """The run's taxonomy replaces the published one. A category no longer in it is removed; its items (of
        venues the run did not crawl) wait to be classified again."""
        staged = list(StagedFoodCategory.objects.filter(run=self.run))
        gone = FoodCategory.objects.exclude(uidentifier__in=[category.uidentifier for category in staged])
        MenuItem.objects.filter(category__in=gone).update(category=None, method=Method.PENDING, confidence=0)
        _, deleted = gone.delete()
        FoodCategory.objects.bulk_create(
            [FoodCategory(uidentifier=category.uidentifier, family=category.family, name=category.name,
                          parent=category.parent, is_generic_or_other=category.is_generic_or_other)
             for category in staged],
            update_conflicts=True, unique_fields=["uidentifier"],
            update_fields=["family", "name", "parent", "is_generic_or_other"])
        return len(staged), deleted.get(FoodCategory._meta.label, 0)

    def _publish_items(self) -> set[tuple[int, str]]:
        """Upserts the staged items of the linked venues; a category a person corrected, maybe while the run was
        going, wins. Returns the (venue pk, item id) published."""
        venue_pk = dict(self.linked_venues.values_list("external_id", "pk"))
        category_pk = dict(FoodCategory.objects.values_list("uidentifier", "pk"))
        decided_by_people = {(venue, item_id): fields for venue, item_id, *fields in MenuItem.objects.filter(
            venue__in=self.linked_venues, method=Method.MANUAL).values_list("venue_id", "item_id",
                                                                            *FIELDS_KEPT_BY_PEOPLE)}
        staged = (StagedMenuItem.objects.filter(run=self.run, venue__external_id__in=venue_pk)
                  .values("venue__external_id", "item_id", "category__uidentifier", *ITEM_FIELDS).order_by("pk"))
        published, rows = set(), []
        for item in staged.iterator(chunk_size=BATCH_SIZE):
            venue = venue_pk[item["venue__external_id"]]
            row = MenuItem(venue_id=venue, item_id=item["item_id"], run=self.run,
                           category_id=category_pk.get(item["category__uidentifier"]),
                           **{field: item[field] for field in ITEM_FIELDS})
            decided = decided_by_people.get((venue, row.item_id))
            if decided is not None:
                for field, value in zip(FIELDS_KEPT_BY_PEOPLE, decided, strict=True):
                    setattr(row, field, value)
            rows.append(row)
            published.add((venue, row.item_id))
            if len(rows) == BATCH_SIZE:
                upsert_items(rows)
                rows = []
        upsert_items(rows)
        return published

    def _remove_items_not_published(self, published: set[tuple[int, str]]) -> int:
        """Items of the linked venues no longer on their menus, and items of venues no longer linked."""
        current = MenuItem.objects.filter(venue__in=self.linked_venues).values_list("pk", "venue_id", "item_id")
        gone = [item_pk for item_pk, venue, item_id in current if (venue, item_id) not in published]
        _, removed = MenuItem.objects.filter(pk__in=gone).delete()
        _, unlinked = MenuItem.objects.exclude(venue__google_matches__status__in=LINKED_MATCH_STATUSES).delete()
        return removed.get(MenuItem._meta.label, 0) + unlinked.get(MenuItem._meta.label, 0)
