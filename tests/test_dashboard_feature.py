import pytest
from django.contrib.auth.models import Group, User
from pytest_bdd import given, parsers, scenarios, then, when

from apps.pipeline import run_services
from apps.pipeline.models import Status

scenarios("dashboard.feature")

pytestmark = pytest.mark.django_db


@pytest.fixture
def context():
    return {}


@given("Just Eat serves the curated venues")
def curated_venues(just_eat):
    """Tiflis, and a venue that no longer exists (see the just_eat fixture)."""


@given("a run that finished processing")
def finished_run(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        run = run_services.create_run()
        run_services.dispatch_waiting_runs(only=[run.pk])
    run.refresh_from_db()
    assert run.status == Status.SUCCEEDED, run.error_message


@given("I am logged in as a dashboard user")
def dashboard_user(client):
    user = User.objects.create_user("analyst", password="a-long-test-password")
    user.groups.add(Group.objects.get(name="Dashboard"))
    client.force_login(user)


@when("I open the dashboard summary")
def open_summary(client, context):
    context["response"] = client.get("/api/dashboard/summary/")


@then(parsers.parse("I see {matched:d} matched restaurant out of {crawled:d} crawled"))
def matched_restaurants(context, matched, crawled):
    kpi = context["response"].json()["matched"]
    assert (kpi["matched"], kpi["crawled"]) == (matched, crawled)


@then(parsers.parse("I see {review:d} restaurants in review and {rejected:d} rejected"))
def review_and_rejected(context, review, rejected):
    groups = context["response"].json()["match_groups"]
    assert (groups["review"], groups["rejected"]) == (review, rejected)


@then(parsers.parse('"{category}" is among the top food categories'))
def top_category(client, category):
    keys = [row["key"] for row in client.get("/api/dashboard/categories/", {"family": "food", "top": 50}).json()]
    assert category in keys


@then("access is denied")
def access_denied(context):
    assert context["response"].status_code == 403
