"""Classifies the menu items of the Just Eat venues a run crawled and linked to their Google place.

Only after the run's own crawl and matching succeeded, and only for the venues that run crawled whose link is
ACCEPTED (by the run) or CONFIRMED (by a person): a venue in REVIEW waits for a person. Every item of those venues
gets a StagedMenuItem row, with or without a category (chopsticks have none); publish_run copies them to MenuItem.

Each run reads its taxonomy file (PipelineRun.food_categories_file, SHA-256 recorded in the run). An item keeps
its published classification when its text did not change; the rest are classified (all of them by default; with
a CATEGORIZATION_MAX_ITEMS_PER_RUN cap, those never classified first, the others wait for the next runs). A category
corrected by a person is never overwritten. The result is also written to `menu_items.json` in the run folder.

The classification itself (rules, then embeddings) is the `categorization` library; this module feeds it and stores
what it returns.
"""

import functools
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Case, Count, Exists, F, IntegerField, OuterRef, Q, Value, When
from django.utils import timezone

from apps.menus.constants import (
    BATCH_SIZE,
    CLASSIFICATION_FIELDS,
    MAX_TEXT_LENGTH,
    MENUS_PER_QUERY,
    OUTPUT_NAME,
)
from apps.menus.menu_helpers import menu_items
from apps.menus.models import MenuItem, Method, StagedFoodCategory, StagedMenuItem
from apps.pipeline.constants import CRAWL_STEP, MATCH_STEP
from apps.pipeline.file_helpers import file_sha256
from apps.pipeline.models import PipelineRun
from apps.pipeline.steps import require_succeeded
from apps.venues.models import MatchStatus, Source, StagedVenue, VenueMatch
from libs.categorization.classifier import Classifier
from libs.categorization.constants import LOW_CONFIDENCE, REFERENCE_CONFIDENCE
from libs.categorization.domain import MenuItemText
from libs.categorization.embeddings import Embedder, FastEmbedder
from libs.categorization.keywords import KeywordRules
from libs.categorization.taxonomy import Taxonomy, TaxonomyFileError, read_taxonomy

logger = logging.getLogger(__name__)

FROM_SETTINGS = object()  # default of `embedder`: the model configured in the settings


@dataclass(frozen=True)
class CategorizeResult:
    venues: int  # Just Eat venues of the run with an accepted or confirmed link
    items: int  # their menu items
    created: int  # not published yet
    removed: int  # published, no longer on the menu of a linked venue
    classified: int  # by this run
    pending: int  # left for the next runs (over CATEGORIZATION_MAX_ITEMS_PER_RUN)
    manual: int  # corrected by a person, kept as they are
    low_confidence: int  # with a category of confidence below LOW_CONFIDENCE
    by_method: dict
    embeddings: bool
    output_file: str

    def as_metrics(self) -> dict:
        return dict(self.__dict__)


def categorize_run_items(run: PipelineRun, *, embedder: Embedder | None = FROM_SETTINGS) -> CategorizeResult:
    require_succeeded(run, CRAWL_STEP, MATCH_STEP)
    if embedder is FROM_SETTINGS:
        embedder = settings_embedder()
    return RunCategorization(run, embedder).categorize()


@functools.cache
def settings_embedder() -> Embedder | None:
    """The local embedding model of the settings, loaded once per worker; None when not configured."""
    path = settings.CATEGORIZATION_EMBEDDING_MODEL_PATH
    if not path:
        logger.warning("CATEGORIZATION_EMBEDDING_MODEL_PATH not set: menu items are classified by rules only")
        return None
    return FastEmbedder(settings.CATEGORIZATION_EMBEDDING_MODEL, path)


def read_run_taxonomy(run: PipelineRun) -> Taxonomy:
    """The run's taxonomy file, its SHA-256 recorded in the run. It must still have every category the keyword
    rules use: a taxonomy that drops one needs the rules reviewed first, so the run fails before changing anything."""
    if not run.food_categories_file:
        raise TaxonomyFileError("no food categories file configured (FOOD_CATEGORIES_FILE)")
    taxonomy = read_taxonomy(run.food_categories_file)
    run.food_categories_sha256 = file_sha256(Path(run.food_categories_file))
    run.save(update_fields=["food_categories_sha256"])
    try:
        KeywordRules({category.name for category in taxonomy.categories})
    except ValueError as error:
        raise TaxonomyFileError(str(error)) from error
    return taxonomy


def linked_venues(run: PipelineRun) -> list[StagedVenue]:
    """The Just Eat venues of the run with a link accepted by the run, or confirmed by a person, as publish_run
    will leave it: a confirmed link whose Google place left the run's file goes back to review (unless a person
    confirmed it again since), and one in review because its place had left is confirmed again if the place is
    back in the file. Loaded without their menus."""
    in_file = Exists(StagedVenue.objects.filter(run=run, source=Source.GOOGLE,
                                                external_id=OuterRef("google__external_id")))
    confirmed = VenueMatch.objects.filter(
        Q(status=MatchStatus.CONFIRMED, google_missing=True) | Q(status=MatchStatus.CONFIRMED, google_missing=False)
        & in_file | Q(status=MatchStatus.REVIEW, google_missing=True) & in_file).values("just_eat__external_id")
    return list(StagedVenue.objects.filter(run=run, source=Source.JUST_EAT)
                .filter(Q(google_matches__status=MatchStatus.ACCEPTED) | Q(external_id__in=confirmed))
                .defer("menus", "opening_times", "details").distinct().order_by("pk"))


def keep_published_classification(row: StagedMenuItem, item: dict, published: tuple,
                                  category_by_uidentifier: dict[str, StagedFoodCategory]) -> None:
    """The staged `row` keeps the classification of its published version when its text did not change, or when a
    person corrected it; otherwise it stays PENDING. Never if it was never classified or its category is gone."""
    (section, name, description, method, category_uidentifier, confidence, is_combo, evidence,
     classified_at) = published
    category = category_by_uidentifier.get(category_uidentifier) if category_uidentifier else None
    if method == Method.PENDING or (category_uidentifier and category is None):
        return
    same_text = (section, name, description) == (item["section"], item["name"], item["description"])
    if method == Method.MANUAL or same_text:
        row.category, row.method, row.confidence, row.is_combo = category, method, confidence, is_combo
        row.evidence, row.classified_at = evidence, classified_at


def to_text(item: StagedMenuItem) -> MenuItemText:
    return MenuItemText(item.name, item.section, item.description)


class RunCategorization:
    """The categorization of one run: stage its taxonomy and items, classify what needs it, export the result."""

    def __init__(self, run: PipelineRun, embedder: Embedder | None) -> None:
        self.run = run
        self.embedder = embedder
        self.taxonomy = read_run_taxonomy(run)
        self.classifier = Classifier(self.taxonomy, embedder)
        self.venues = linked_venues(run)
        self.items = StagedMenuItem.objects.filter(run=run)

    def categorize(self) -> CategorizeResult:
        with transaction.atomic():  # a step retried by the queue starts again
            StagedMenuItem.objects.filter(run=self.run).delete()
            StagedFoodCategory.objects.filter(run=self.run).delete()
            categories = self._stage_taxonomy()
            created, removed = self._stage_items(categories)
        to_classify = list(self._classification_queue())
        self._classify(to_classify, categories)
        output = self._export()

        by_method = dict(self.items.values_list("method").annotate(items=Count("id")).order_by())
        low_confidence = (self.items.filter(category__isnull=False, confidence__lt=LOW_CONFIDENCE)
                          .exclude(method=Method.MANUAL).count())
        result = CategorizeResult(
            venues=len(self.venues), items=self.items.count(), created=created, removed=removed,
            classified=len(to_classify), pending=by_method.get(Method.PENDING, 0),
            manual=by_method.get(Method.MANUAL, 0), low_confidence=low_confidence, by_method=by_method,
            embeddings=self.embedder is not None, output_file=str(output))
        logger.info("run=%s categorization: %s", self.run.pk, result)
        return result

    def _stage_taxonomy(self) -> dict[str, StagedFoodCategory]:
        rows = StagedFoodCategory.objects.bulk_create([
            StagedFoodCategory(run=self.run, uidentifier=category.uidentifier, family=category.family,
                               name=category.name, parent=category.parent,
                               is_generic_or_other=category.is_generic_or_other)
            for category in self.taxonomy.categories])
        return {category.name: category for category in rows}

    def _stage_items(self, categories: dict[str, StagedFoodCategory]) -> tuple[int, int]:
        """Stages every item of the venues' menus; see keep_published_classification.
        Returns (items not published yet, published items of these venues no longer on their menus)."""
        category_by_uidentifier = {category.uidentifier: category for category in categories.values()}
        published = {(venue_id, item_id): rest for venue_id, item_id, *rest in MenuItem.objects.filter(
            venue__source=Source.JUST_EAT, venue__external_id__in=[venue.external_id for venue in self.venues])
            .values_list("venue__external_id", "item_id", "section", "name", "description", "method",
                         "category__uidentifier", "confidence", "is_combo", "evidence", "classified_at")}
        created = 0
        for start in range(0, len(self.venues), MENUS_PER_QUERY):
            chunk = self.venues[start:start + MENUS_PER_QUERY]
            menus_by_venue = dict(StagedVenue.objects.filter(pk__in=[venue.pk for venue in chunk])
                                  .values_list("pk", "menus"))
            rows = []
            for venue in chunk:
                for item_id, item in menu_items(menus_by_venue[venue.pk]).items():
                    row = StagedMenuItem(run=self.run, venue=venue, item_id=item_id, **item)
                    known = published.pop((venue.external_id, item_id), None)
                    if known is None:
                        created += 1
                    else:
                        keep_published_classification(row, item, known, category_by_uidentifier)
                    rows.append(row)
            StagedMenuItem.objects.bulk_create(rows, batch_size=BATCH_SIZE)
        return created, len(published)

    def _classification_queue(self):
        """Items to classify in this run: never classified (or changed) first, then the oldest classified ones."""
        queue = (self.items.exclude(method=Method.MANUAL)
                 .annotate(waiting=Case(When(method=Method.PENDING, then=Value(0)), default=Value(1),
                                        output_field=IntegerField()))
                 .order_by("waiting", F("classified_at").asc(nulls_first=True), "pk"))
        limit = settings.CATEGORIZATION_MAX_ITEMS_PER_RUN
        return queue[:limit] if limit else queue

    def _classify(self, to_classify: list[StagedMenuItem], categories: dict[str, StagedFoodCategory]) -> None:
        references = self._references() if self.embedder and to_classify else []
        results = self.classifier.classify([to_text(item) for item in to_classify], references)
        now = timezone.now()
        for item, result in zip(to_classify, results, strict=True):
            item.category = categories[result.category.name] if result.category else None
            item.confidence, item.method, item.is_combo = result.confidence, result.method.value, result.is_combo
            item.evidence, item.classified_at = result.evidence[:MAX_TEXT_LENGTH], now
        StagedMenuItem.objects.bulk_update(to_classify, CLASSIFICATION_FIELDS, batch_size=BATCH_SIZE)

    def _references(self) -> list[tuple[MenuItemText, str]]:
        """Published items classified with high confidence on other venues, and every manual correction, to teach
        the embeddings (the items of this run's venues are classified now and teach them with their new
        categories)."""
        rows = (MenuItem.objects.filter(category__isnull=False)
                .filter(Q(method=Method.MANUAL)
                        | (Q(confidence__gte=REFERENCE_CONFIDENCE, method__in=[Method.NAME, Method.SECTION])
                           & ~Q(venue__external_id__in=[venue.external_id for venue in self.venues])))
                .values_list("name", "section", "description", "category__name"))
        return [(MenuItemText(name, section, description), category)
                for name, section, description, category in rows]

    def _export(self) -> Path:
        """menu_items.json in the run folder: one entry per item, as in the challenge statement (plus its menus,
        confidence and method). Written to a temporary file first, so a reader never sees half of it."""
        crawl_dir = self.run.steps.filter(name=CRAWL_STEP).values_list("output_dir", flat=True).first()
        folder = Path(crawl_dir) if crawl_dir else Path(settings.PIPELINE_OUTPUT_DIR) / f"run-{self.run.pk}"
        folder.mkdir(parents=True, exist_ok=True)
        # values(): plain dicts, without loading each item's venue (and its menus, up to MBs each) into memory.
        rows = [{
            "venue_id": item["venue__external_id"],
            "venue_name": item["venue__name"],
            "menu_ids": item["menu_ids"],
            "item_id": item["item_id"],
            "item_name": item["name"],
            "section": item["section"],
            "category_uidentifier": item["category__uidentifier"],
            "name": item["category__name"],
            "parent": item["category__parent"],
            "family": item["category__family"],
            "confidence": item["confidence"],
            "method": item["method"],
            "is_combo": item["is_combo"],
        } for item in self.items.order_by("venue__external_id", "section", "item_id").values(
            "venue__external_id", "venue__name", "menu_ids", "item_id", "name", "section", "category__uidentifier",
            "category__name", "category__parent", "category__family", "confidence", "method", "is_combo")]
        path = folder / OUTPUT_NAME
        partial = path.with_suffix(".partial.json")
        partial.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        partial.replace(path)
        return path
