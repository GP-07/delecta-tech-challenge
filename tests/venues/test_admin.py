import pytest
from django.urls import reverse

from apps.venues.models import MatchStatus, VenueMatch
from tests.conftest import TIFLIS_ID
from tests.runs import published_run

pytestmark = pytest.mark.django_db


@pytest.fixture
def link(tiflis_expected):
    published_run({TIFLIS_ID: tiflis_expected})
    return VenueMatch.objects.get()


@pytest.mark.parametrize(("action", "status"), [("confirm", MatchStatus.CONFIRMED), ("reject", MatchStatus.REJECTED)])
def test_staff_review_links_from_the_admin(admin_client, admin_user, link, action, status):
    url = reverse("admin:venues_venuematch_changelist")

    response = admin_client.post(url, {"action": action, "_selected_action": [link.pk]})

    assert response.status_code == 302
    link.refresh_from_db()
    assert (link.status, link.reviewed_by) == (status, admin_user)


def test_the_links_list_shows_both_venues(admin_client, link):
    response = admin_client.get(reverse("admin:venues_venuematch_changelist"))

    assert response.status_code == 200
    assert "Tiflis Restaurant" in response.content.decode()


def test_anonymous_users_cannot_see_the_links(client, link):
    response = client.get(reverse("admin:venues_venuematch_changelist"))

    assert response.status_code == 302  # to the login page
