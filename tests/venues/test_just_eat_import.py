import pytest

from apps.pipeline.run_services import create_run
from apps.venues.just_eat_import_services import load_just_eat_venues
from apps.venues.models import Source, StagedVenue, Venue
from tests.conftest import TIFLIS_ID

pytestmark = pytest.mark.django_db


def test_a_crawled_venue_is_staged_for_its_run(tiflis_expected):
    run = create_run()

    stats = load_just_eat_venues({TIFLIS_ID: tiflis_expected}, run=run)

    assert stats.staged == 1
    venue = StagedVenue.objects.get(run=run, source=Source.JUST_EAT, external_id=TIFLIS_ID)
    assert (venue.name, venue.brand, venue.unique_name) == ("Tiflis Restaurant", None, "tiflis-restaurant-barcelona")
    assert (venue.city, venue.address, venue.postal_code) == ("Barcelona", "Carrer del Consell de Cent, 487", "08013")
    assert (venue.latitude, venue.longitude) == (41.399772, 2.177098)  # GeoJSON is [longitude, latitude]
    assert (venue.rating_count, venue.star_rating) == (18, 0)
    assert venue.cuisines == ["medio-oriente", "cocina-arabe"]
    assert venue.store_front_type == tiflis_expected["storeFrontType"]
    assert venue.menus == tiflis_expected["menus"]
    assert venue.opening_times == tiflis_expected["openingTimes"]


def test_staging_never_touches_the_published_venues(tiflis_expected):
    load_just_eat_venues({TIFLIS_ID: tiflis_expected}, run=create_run())

    assert not Venue.objects.exists()


def test_a_step_retried_stages_its_venues_again_from_scratch(tiflis_expected):
    run = create_run()
    load_just_eat_venues({TIFLIS_ID: tiflis_expected, "1": {**tiflis_expected, "name": "Other"}}, run=run)

    load_just_eat_venues({TIFLIS_ID: tiflis_expected}, run=run)

    assert list(StagedVenue.objects.values_list("external_id", flat=True)) == [TIFLIS_ID]


def test_each_run_has_its_own_staged_venues(tiflis_expected):
    first, second = create_run(), create_run()

    load_just_eat_venues({TIFLIS_ID: tiflis_expected}, run=first)
    load_just_eat_venues({TIFLIS_ID: {**tiflis_expected, "name": "Tiflis"}}, run=second)

    assert StagedVenue.objects.get(run=first).name == "Tiflis Restaurant"
    assert StagedVenue.objects.get(run=second).name == "Tiflis"
