"""What each chart of the dashboard shows, computed from the published tables. Read-only: nothing here changes data.

Everything is about one run, the last one published (`PipelineRun.objects.last_published()`): the Just Eat venues
it crawled, how they are matched to Google, and the menu items of the matched ones. Links are read as they are
now, so a decision taken in the admin after the run (confirm, reject) shows up right away.

The querysets of the models do the filtering (`Venue.objects.crawled_by(run).linked()`, `MenuItem.objects
.of_venues(...).categorized()`); DashboardService has one method per chart and only chains them. What each answer
looks like is the contract of the API, in serializers.py: prices, scores and distances are rounded there.

    Main view                                        "More detail" (loaded when unfolded)
        run_info()          run, duration, steps         dishes(group)    dishes of matched venues, by group
        matched_restaurants()  the required KPI          menus()          size of the menus, drinks, combos
        match_groups()      venues per match group       quality()        what decided each category, confidence
        venues(group)       the venues of a group
        top_categories()    top food offerings by category
        category_detail()   one category, on click
"""

import statistics

from django.db.models import Aggregate, Count, FloatField, Prefetch, Q, QuerySet
from django.db.models.functions import Lower

from apps.dashboard.constants import CONFIDENCE_BUCKETS, TOP_ROWS
from apps.menus.models import FoodCategory, MenuItem, Method
from apps.pipeline.models import PipelineRun
from apps.venues.choices import MatchGroup
from apps.venues.models import Venue, VenueMatch
from apps.venues.querysets import match_group_condition


class CategoryNotFoundError(LookupError):
    pass


class Median(Aggregate):
    function = "percentile_cont"
    template = "%(function)s(0.5) WITHIN GROUP (ORDER BY %(expressions)s)"
    output_field = FloatField()


def median_price() -> Median:
    """Median price of the dishes; a combo is not the price of its dish."""
    return Median("price", filter=Q(is_combo=False, price__gt=0))


def duration_seconds(record) -> int | None:
    """Of a run or a step, once finished."""
    if not (record.started_at and record.finished_at):
        return None
    return round((record.finished_at - record.started_at).total_seconds())


def count_between(queryset: QuerySet, field: str, low: float, high: float | None) -> int:
    """Rows with low <= field < high (no upper limit when `high` is None)."""
    queryset = queryset.filter(**{f"{field}__gte": low})
    return (queryset.filter(**{f"{field}__lt": high}) if high is not None else queryset).count()


class DashboardService:
    """The charts of the dashboard for one published run."""

    def __init__(self, run: PipelineRun) -> None:
        self.run = run

    # --- main view ----------------------------------------------------------------------------------------

    def run_info(self) -> dict:
        """Which run is shown, how long it took, and whether a later run is going or failed (it changed nothing:
        only a published run does)."""
        newer = PipelineRun.objects.started_after(self.run).order_by("-pk").first()
        return {
            "id": self.run.pk, "finished_at": self.run.finished_at, "seconds": duration_seconds(self.run),
            "newer_run": newer and {"id": newer.pk, "status": newer.status},
            "steps": [{"name": step.name, "status": step.status, "seconds": duration_seconds(step)}
                      for step in self.run.steps.all()],
        }

    def matched_restaurants(self) -> dict:
        """The required KPI: matched restaurants (accepted or confirmed) out of the crawled ones."""
        crawled = Venue.objects.crawled_by(self.run)
        return {"matched": crawled.linked().count(), "crawled": crawled.count()}

    def match_groups(self) -> dict[str, int]:
        """Crawled venues per match group; every venue is in exactly one, so they add up to the crawled total."""
        return Venue.objects.crawled_by(self.run).aggregate(
            **{group: Count("pk", filter=match_group_condition(group)) for group in MatchGroup.values})

    def venues(self, group: str) -> QuerySet[Venue]:
        """The venues of a match group, with their Google place, for a paginated list (see VenueRowSerializer)."""
        shown_matches = VenueMatch.objects.select_related("google").defer("google__details").order_by("-updated_at")
        return (Venue.objects.crawled_by(self.run).in_match_group(group).without_large_fields()
                .prefetch_related(Prefetch("google_matches", queryset=shown_matches)).order_by("name", "pk"))

    def top_categories(self, *, family: str, level: str = "parent", order: str = "venues",
                       top: int = 10) -> list[dict]:
        """Top food (or drink) offerings: categories ranked by the matched restaurants offering them (or by
        dishes), with their median price."""
        linked = Venue.objects.crawled_by(self.run).linked()
        linked_count = linked.count()
        field = f"category__{level}"
        rows = (MenuItem.objects.of_venues(linked).categorized(family).values(field)
                .annotate(items=Count("pk"), venues=Count("venue", distinct=True), median_price=median_price())
                .order_by(f"-{order}", "-items" if order == "venues" else "-venues", field)[:top])
        return [{"key": row[field], "family": family, "items": row["items"], "venues": row["venues"],
                 "venues_share": round(row["venues"] / linked_count, 4) if linked_count else 0,
                 "median_price": row["median_price"]}
                for row in rows]

    def category_detail(self, *, level: str, key: str) -> dict:
        """One category (or group of categories): its sub-categories, most frequent dishes and restaurants."""
        category = FoodCategory.objects.filter(**{level: key}).first()
        if category is None:
            raise CategoryNotFoundError(key)
        items = (MenuItem.objects.of_venues(Venue.objects.crawled_by(self.run).linked()).categorized()
                 .filter(**{f"category__{level}": key}))
        totals = items.aggregate(items=Count("pk"), venues=Count("venue", distinct=True), median_price=median_price())
        subcategories = []
        if level == "parent":
            subcategories = [
                {"key": row["category__name"], "items": row["items"], "venues": row["venues"],
                 "median_price": row["median_price"]}
                for row in items.values("category__name").annotate(
                    items=Count("pk"), venues=Count("venue", distinct=True), median_price=median_price(),
                ).order_by("-items", "category__name")
            ]
        dishes = (items.annotate(dish=Lower("name")).values("dish")
                  .annotate(items=Count("pk"), median_price=median_price()).order_by("-items", "dish")[:TOP_ROWS])
        venues = items.values("venue__name").annotate(items=Count("pk")).order_by("-items", "venue__name")[:TOP_ROWS]
        return {
            "key": key, "level": level, "family": category.family, "items": totals["items"],
            "venues": totals["venues"], "median_price": totals["median_price"],
            "subcategories": subcategories,
            "top_dishes": [{"name": dish["dish"], "items": dish["items"], "median_price": dish["median_price"]}
                           for dish in dishes],
            "top_venues": [{"name": venue["venue__name"], "items": venue["items"]} for venue in venues],
        }

    # --- "more detail" --------------------------------------------------------------------------------------

    def dishes(self, group: str) -> QuerySet:
        """The dishes of the venues of a matched group (accepted or confirmed), for a paginated list (see
        DishRowSerializer). Only matched venues have their dishes categorized and stored."""
        venues = Venue.objects.crawled_by(self.run).in_match_group(group)
        return (MenuItem.objects.of_venues(venues)
                .order_by("venue__name", "section", "name", "pk")
                .values("pk", "venue__name", "name", "section", "category__name", "category__parent",
                        "category__family", "confidence", "method", "price"))

    def menus(self) -> dict:
        """Size of the menus of the matched venues, how many sell drinks, and how much of them are combos."""
        items = MenuItem.objects.of_venues(Venue.objects.crawled_by(self.run).linked())
        per_venue = list(items.values("venue").annotate(items=Count("pk"),
                                                        drinks=Count("pk", filter=Q(category__family="drink"))))
        totals = items.aggregate(items=Count("pk"), combos=Count("pk", filter=Q(is_combo=True)))
        return {
            "venues": len(per_venue),
            "median_items": statistics.median(venue["items"] for venue in per_venue) if per_venue else None,
            "venues_with_drinks": (round(sum(venue["drinks"] > 0 for venue in per_venue) / len(per_venue), 4)
                                   if per_venue else 0),
            "combo_share": round(totals["combos"] / totals["items"], 4) if totals["items"] else 0,
        }

    def quality(self) -> dict:
        """How the dishes were categorized: how many, what decided each category, and with what confidence."""
        items = MenuItem.objects.of_venues(Venue.objects.crawled_by(self.run).linked())
        categorized = items.categorized()
        labels = dict(Method.choices)
        methods = items.values("method").annotate(items=Count("pk")).order_by("-items", "method")
        return {
            "items": {"total": items.count(), "categorized": categorized.count(),
                      "low_confidence": items.low_confidence().count(),
                      "pending": items.filter(method=Method.PENDING).count()},
            "methods": [{"method": method["method"], "label": labels[method["method"]], "items": method["items"]}
                        for method in methods],
            "confidence": [{"bucket": label, "items": count_between(categorized, "confidence", low, high)}
                           for label, low, high in CONFIDENCE_BUCKETS],
        }
