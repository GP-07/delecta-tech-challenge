import pytest
from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.urls import reverse

from apps.dashboard.constants import LOCKED_MESSAGE
from apps.pipeline.models import PipelineRun

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()  # failed logins and request budgets
    yield
    cache.clear()


@pytest.fixture
def viewer(client):
    user = User.objects.create_user("viewer", password="a-long-test-password")
    user.groups.add(Group.objects.get(name="Dashboard"))
    client.force_login(user)
    return client


@pytest.fixture
def index_file(settings, tmp_path):
    settings.DASHBOARD_INDEX_FILE = str(tmp_path / "index.html")
    (tmp_path / "index.html").write_text("<div id='root'></div>")


def get(client, name, **params):
    return client.get(reverse(name), params)


@pytest.mark.parametrize("name", ["dashboard-summary", "dashboard-categories", "dashboard-venues"])
def test_the_api_needs_a_login(client, pipeline, name):
    assert get(client, name).status_code == 403


def test_users_outside_the_dashboard_group_cannot_see_it(client, pipeline, index_file):
    client.force_login(User.objects.create_user("other", password="a-long-test-password"))

    assert get(client, "dashboard-summary").status_code == 403
    assert get(client, "dashboard").status_code == 403


def test_the_page_sends_anonymous_users_to_the_login(client, index_file):
    response = get(client, "dashboard")

    assert (response.status_code, response.url) == (302, "/accounts/login/?next=/dashboard/")


def test_the_page_is_the_frontend_build(viewer, index_file):
    response = get(viewer, "dashboard")

    assert (response.status_code, response.content) == (200, b"<div id='root'></div>")
    assert "script-src 'self'" in response["Content-Security-Policy"]
    assert "csrftoken" in response.cookies  # to log out


def test_without_the_frontend_build_the_page_says_how_to_build_it(viewer, settings, tmp_path):
    settings.DASHBOARD_INDEX_FILE = str(tmp_path / "missing.html")

    assert get(viewer, "dashboard").status_code == 503


def test_a_dashboard_user_sees_the_kpis(viewer, pipeline):
    response = get(viewer, "dashboard-summary")

    assert response.status_code == 200
    body = response.json()
    assert (body["run"]["id"], body["matched"]["matched"], body["match_groups"]["review"]) == (pipeline.pk, 2, 1)
    assert "frame-ancestors 'none'" in response["Content-Security-Policy"]


def test_superusers_see_it_too(admin_client, pipeline):
    assert get(admin_client, "dashboard-summary").status_code == 200


def test_the_api_only_reads(viewer, pipeline):
    assert viewer.post(reverse("dashboard-summary")).status_code == 405


@pytest.mark.parametrize("params", [{"top": 500}, {"level": "uidentifier"}, {"family": "'; drop table x"}])
def test_only_known_parameter_values_are_accepted(viewer, pipeline, params):
    assert get(viewer, "dashboard-categories", **params).status_code == 400


def test_top_categories(viewer, pipeline):
    response = get(viewer, "dashboard-categories", family="food", level="parent", top=1)

    assert [category["key"] for category in response.json()] == ["pizza"]


def test_category_detail(viewer, pipeline):
    assert get(viewer, "dashboard-category", level="parent", key="pizza").json()["items"] == 4
    assert get(viewer, "dashboard-category", level="parent", key="pasta").status_code == 404


def test_venues_of_a_match_group_are_paginated(viewer, pipeline):
    body = get(viewer, "dashboard-venues", group="accepted").json()

    assert (body["count"], [venue["name"] for venue in body["results"]]) == (1, ["Pizzeria Uno"])
    assert get(viewer, "dashboard-venues").status_code == 400  # the group is required


def test_dishes_of_a_matched_group_are_paginated(viewer, pipeline):
    body = get(viewer, "dashboard-dishes", group="accepted").json()

    assert (body["count"], body["results"][0]["venue"], body["results"][0]["price"]) == (4, "Pizzeria Uno", 2.0)


@pytest.mark.parametrize("group", ["review", "rejected", "unmatched", "matched"])
def test_only_matched_groups_have_dishes(viewer, pipeline, group):
    assert get(viewer, "dashboard-dishes", group=group).status_code == 400


@pytest.mark.parametrize("name", ["dashboard-menus", "dashboard-quality"])
def test_details(viewer, pipeline, name):
    assert get(viewer, name).status_code == 200


def test_without_a_finished_run_there_is_nothing_to_show(viewer):
    PipelineRun.objects.create()

    response = get(viewer, "dashboard-summary")

    assert (response.status_code, response.json()) == (404, {"detail": "Todavía no hay corridas terminadas."})


def test_the_admin_keeps_its_own_headers(admin_client):
    assert "Content-Security-Policy" not in admin_client.get("/admin/")


def test_login_takes_to_the_dashboard(client):
    User.objects.create_user("viewer", password="a-long-test-password")

    response = client.post(reverse("login"), {"username": "viewer", "password": "a-long-test-password"})

    assert (response.status_code, response.url) == (302, "/dashboard/")


def test_after_too_many_failed_logins_even_the_right_password_is_refused(client, settings):
    User.objects.create_user("viewer", password="a-long-test-password")
    for _ in range(settings.LOGIN_MAX_FAILURES):
        client.post(reverse("login"), {"username": "viewer", "password": "wrong"})

    response = client.post(reverse("login"), {"username": "viewer", "password": "a-long-test-password"})

    assert response.status_code == 200
    assert LOCKED_MESSAGE in response.content.decode()
