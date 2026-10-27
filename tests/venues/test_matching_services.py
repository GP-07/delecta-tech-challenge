import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from apps.pipeline.run_services import create_run
from apps.pipeline.steps import StepNotDoneError
from apps.venues import review_services
from apps.venues.just_eat_import_services import load_just_eat_venues
from apps.venues.matching_services import match_run_venues
from apps.venues.models import MatchStatus, Source, StagedVenueMatch, Venue, VenueMatch
from tests.conftest import TIFLIS_ID
from tests.runs import published_run, staged_run, succeeded

pytestmark = pytest.mark.django_db

TIFLIS_PLACE = "ChIJqTJI7ESjpBIR7jRF8cSRyDI"
NEIGHBOUR_PLACE = "ChIJaQU4xg-jpBIRqlFZQdD4yOo"  # "A Toda Leña", same building


def staged_links(run):
    return set(StagedVenueMatch.objects.filter(run=run).values_list(
        "just_eat__external_id", "google__external_id", "status"))


def test_the_crawled_venues_are_linked_to_their_google_place(tiflis_expected):
    run = staged_run({TIFLIS_ID: tiflis_expected})

    result = match_run_venues(run)

    assert (result.venues, result.accepted, result.review, result.unmatched) == (1, 1, 0, 0)
    assert staged_links(run) == {(TIFLIS_ID, TIFLIS_PLACE, MatchStatus.ACCEPTED)}
    match = StagedVenueMatch.objects.get()
    assert match.same_address and match.distance_m < 1
    assert match.evidence["name_score"] == pytest.approx(1)
    assert not VenueMatch.objects.exists()  # nothing is published by the matching


@pytest.mark.parametrize("missing", ["crawl_just_eat", "load_google_venues"])
def test_matching_needs_the_run_own_crawl_and_google_load(tiflis_expected, settings, missing):
    from apps.venues.google_import_services import load_google_venues

    run = create_run()
    load_just_eat_venues({TIFLIS_ID: tiflis_expected}, run=run)  # data staged, but a step never finished
    load_google_venues(settings.GOOGLE_VENUES_FILE, run=run)
    succeeded(run, *({"crawl_just_eat", "load_google_venues"} - {missing}))

    with pytest.raises(StepNotDoneError, match=missing):
        match_run_venues(run)

    assert not StagedVenueMatch.objects.exists()


def test_only_venues_staged_by_the_run_crawl_are_matched(tiflis_expected):
    staged_run({TIFLIS_ID: tiflis_expected})  # another run

    result = match_run_venues(staged_run({}))

    assert result.venues == 0
    assert not StagedVenueMatch.objects.exists()


def test_a_rejected_pair_is_never_proposed_again(tiflis_expected):
    published_run({TIFLIS_ID: tiflis_expected})
    review_services.reject(VenueMatch.objects.get(), user=None)
    run = staged_run({TIFLIS_ID: tiflis_expected})

    result = match_run_venues(run)

    assert (result.accepted, result.review) == (0, 0)
    assert not staged_links(run) - {(TIFLIS_ID, NEIGHBOUR_PLACE, MatchStatus.REVIEW)}


def test_a_venue_confirmed_by_a_person_is_not_matched_again(tiflis_expected):
    published_run({TIFLIS_ID: tiflis_expected})
    tiflis = Venue.objects.get(source=Source.JUST_EAT, external_id=TIFLIS_ID)
    VenueMatch.objects.all().delete()
    neighbour = Venue.objects.get(source=Source.GOOGLE, external_id=NEIGHBOUR_PLACE)
    VenueMatch.objects.create(just_eat=tiflis, google=neighbour, status=MatchStatus.CONFIRMED, score=0,
                              name_score=0, distance_m=0, same_address=True, reason="by hand")
    run = staged_run({TIFLIS_ID: tiflis_expected})

    result = match_run_venues(run)

    assert result.confirmed == 1
    assert not staged_links(run)


def test_people_confirm_or_reject_links(tiflis_expected):
    published_run({TIFLIS_ID: tiflis_expected})
    match = VenueMatch.objects.get()
    user = get_user_model().objects.create_user("reviewer")

    review_services.confirm(match, user)

    match.refresh_from_db()
    assert (match.status, match.reviewed_by) == (MatchStatus.CONFIRMED, user)
    assert match.reviewed_at is not None


def test_a_venue_has_one_active_link_at_most(tiflis_expected):
    published_run({TIFLIS_ID: tiflis_expected})
    match = VenueMatch.objects.get()
    neighbour = Venue.objects.get(source=Source.GOOGLE, external_id=NEIGHBOUR_PLACE)

    with pytest.raises(IntegrityError):
        VenueMatch.objects.create(just_eat=match.just_eat, google=neighbour, status=MatchStatus.REVIEW, score=0,
                                  name_score=0, distance_m=0, same_address=True, reason="test")
