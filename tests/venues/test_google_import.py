import functools
import json
from pathlib import Path

import pytest

from apps.pipeline.file_helpers import file_sha256
from apps.pipeline.run_services import create_run
from apps.venues.google_import_services import GoogleVenuesFileError, load_google_venues
from apps.venues.models import Source, StagedVenue, Venue
from tests.conftest import load_json

pytestmark = pytest.mark.django_db

TIFLIS_PLACE = "ChIJqTJI7ESjpBIR7jRF8cSRyDI"


@pytest.fixture
def records(settings):
    return load_json(Path(settings.GOOGLE_VENUES_FILE))


def write_records(folder, records, name="google_venues.json"):
    path = folder / name
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


@pytest.fixture
def write(tmp_path):
    """write(records, name=...) -> the path of a Google venues file with those records."""
    return functools.partial(write_records, tmp_path)


def staged(run):
    return StagedVenue.objects.filter(run=run, source=Source.GOOGLE)


def test_google_places_are_staged_for_the_run_with_the_file_hash(settings):
    run = create_run()

    result = load_google_venues(settings.GOOGLE_VENUES_FILE, run=run)

    assert (result.places, result.duplicates) == (3, 1)
    venue = staged(run).get(external_id=TIFLIS_PLACE)
    assert (venue.name, venue.postal_code) == ("Tiflis Restaurant", "08013")
    assert venue.address == "Carrer del Consell de Cent, 487, Eixample, 08013 Barcelona"
    assert (venue.latitude, venue.longitude) == (41.3997805, 2.1770978999999997)
    assert (venue.star_rating, venue.rating_count) == (4.1, 0)
    assert venue.url == "https://maps.google.es/?cid=3659334972285990126"
    assert venue.details["website"] == "https://www.tiflisbarcelona.com/"
    run.refresh_from_db()
    assert run.google_venues_sha256 == result.sha256 == file_sha256(settings.GOOGLE_VENUES_FILE)


def test_every_run_stages_its_own_file_and_the_published_venues_are_untouched(records, write):
    first, second = create_run(), create_run()

    load_google_venues(write(records), run=first)
    load_google_venues(write([{**records[1], "name": "Tiflis"}], "v2.json"), run=second)

    assert staged(first).count() == 3
    assert list(staged(second).values_list("name", flat=True)) == ["Tiflis"]
    assert not Venue.objects.exists()


@pytest.mark.parametrize("change", [
    {"googlePlaceId": "../../etc"},  # ids end up in URLs and lookups: only the expected characters
    {"latitude": 400},
    {"googleMapsUrl": "javascript:alert(1)"},
    {"name": ""},
])
def test_an_invalid_record_rejects_the_whole_file(records, write, change):
    path = write([records[0], {**records[1], **change}])

    with pytest.raises(GoogleVenuesFileError):
        load_google_venues(path, run=create_run())

    assert not StagedVenue.objects.exists()


def test_a_missing_or_unconfigured_file_fails(tmp_path):
    with pytest.raises(GoogleVenuesFileError, match="not found"):
        load_google_venues(tmp_path / "nope.json", run=create_run())
    with pytest.raises(GoogleVenuesFileError, match="GOOGLE_VENUES_FILE"):
        load_google_venues("", run=create_run())


def test_files_over_the_size_limit_are_refused(settings, records, write):
    settings.GOOGLE_VENUES_MAX_BYTES = 10

    with pytest.raises(GoogleVenuesFileError, match="larger"):
        load_google_venues(write(records), run=create_run())


def test_not_a_list_of_places(write):
    with pytest.raises(GoogleVenuesFileError):
        load_google_venues(write({"not": "a list"}), run=create_run())
