"""A small, hand-made pipeline result the dashboard services are checked against.

Run 1 (finished) crawled five Just Eat venues:
    Pizzeria Uno   accepted (Google 4.0)    Margherita 10, Diavola 12, Coca-Cola 2, Menú pizza + bebida 15 (combo)
    Burger Dos     confirmed (Google 4.5)   Classic Burger 9, Pizza Barbacoa 11, Agua 1.5
    Sushi Tres     in review                no items: venues in review are not categorized
    Kebab Cuatro   rejected by a person
    Bar Cinco      no match
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.menus.models import FoodCategory, MenuItem, Method
from apps.pipeline.models import PipelineRun, Status
from apps.venues.models import MatchStatus, Source, Venue, VenueMatch

CATEGORIES = [  # (name, parent, family)
    ("pizza margherita", "pizza", "food"),
    ("pizza other", "pizza", "food"),
    ("burger", "fast food", "food"),
    ("cola", "soft drinks", "drink"),
    ("water", "soft drinks", "drink"),
]


def finished_run(**fields) -> PipelineRun:
    now = timezone.now()
    run = PipelineRun.objects.create(status=Status.SUCCEEDED, started_at=now, finished_at=now, published_at=now,
                                     **fields)
    run.steps.create(name="crawl_just_eat", position=0, status=Status.SUCCEEDED, started_at=now, finished_at=now)
    return run


def venue(run, name, *, source=Source.JUST_EAT, star_rating=None, euro=None, **fields) -> Venue:
    details = {"euroScale": euro} if euro else {}
    return Venue.objects.create(source=source, external_id=f"{source}-{name}", name=name, last_run=run,
                                star_rating=star_rating, details=details, **fields)


def link(run, just_eat, google, status, score=0.9, distance_m=20.0) -> VenueMatch:
    return VenueMatch.objects.create(just_eat=just_eat, google=google, status=status, score=score, name_score=score,
                                     distance_m=distance_m, same_address=True, reason="test", run=run)


def dish(run, venue, name, price, category, *, confidence=0.95, method=Method.NAME, is_combo=False) -> MenuItem:
    return MenuItem.objects.create(
        venue=venue, item_id=f"{venue.name}-{name}", name=name, price=Decimal(str(price)), is_combo=is_combo,
        category=FoodCategory.objects.get(name=category) if category else None, confidence=confidence,
        method=method, run=run)


@pytest.fixture
def pipeline(db):
    for uid, (name, parent, family) in enumerate(CATEGORIES):
        FoodCategory.objects.create(uidentifier=str(uid), name=name, parent=parent, family=family,
                                    is_generic_or_other=name.endswith("other"))
    run = finished_run()
    uno = venue(run, "Pizzeria Uno", star_rating=4.6, rating_count=100, city="Barcelona", cuisines=["pizza"])
    dos = venue(run, "Burger Dos", star_rating=4.2, rating_count=50, city="Barcelona", cuisines=["burgers"])
    tres = venue(run, "Sushi Tres", star_rating=4.8, city="Barcelona")
    cuatro = venue(run, "Kebab Cuatro", city="Barcelona")
    venue(run, "Bar Cinco", city="Barcelona")
    google = {name: venue(run, f"{name} (Google)", source=Source.GOOGLE, star_rating=rating, euro=euro)
              for name, rating, euro in [("Uno", 4.0, "10-20 €"), ("Dos", 4.5, "20-30 €"), ("Tres", 4.4, None),
                                         ("Cuatro", 3.9, None), ("Seis", 4.1, None)]}
    link(run, uno, google["Uno"], MatchStatus.ACCEPTED, score=0.95, distance_m=10)
    link(run, dos, google["Dos"], MatchStatus.CONFIRMED, score=0.7, distance_m=120)
    link(run, tres, google["Tres"], MatchStatus.REVIEW, score=0.6, distance_m=300)
    link(run, cuatro, google["Cuatro"], MatchStatus.REJECTED, score=0.65)
    dish(run, uno, "Margherita", 10, "pizza margherita")
    dish(run, uno, "Diavola", 12, "pizza other", confidence=0.65, method=Method.SECTION)
    dish(run, uno, "Coca-Cola", 2, "cola")
    dish(run, uno, "Menú pizza + bebida", 15, "pizza other", is_combo=True, confidence=0.75)
    dish(run, dos, "Classic Burger", 9, "burger")
    dish(run, dos, "Pizza Barbacoa", 11, "pizza other", confidence=0.4, method=Method.EMBEDDING)
    dish(run, dos, "Agua", 1.5, "water")
    dish(run, dos, "Bolsa", 0.1, None, confidence=0, method=Method.NON_FOOD)
    return run
