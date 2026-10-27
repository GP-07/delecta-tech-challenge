import asyncio
import functools
import io
import json

import pytest
import respx
from django.core.management import CommandError, call_command
from pytest_bdd import given, parsers, scenarios, then, when

from apps.venues.models import Venue
from libs.crawler.constants import CDN_BASE_URL
from tests.conftest import TIFLIS, load_json, serve_recorded_venue

scenarios("crawl_venue.feature")

pytestmark = pytest.mark.django_db


@pytest.fixture
def router():
    with respx.mock(assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setenv("CRAWLER_REQUEST_DELAY_SECONDS", "0")
    monkeypatch.setenv("CRAWLER_BACKOFF_SECONDS", "0")
    return {"output_dir": tmp_path / "output"}


def _run_dir(context):
    (run_dir,) = context["output_dir"].iterdir()  # one run, one folder
    return run_dir


@given(parsers.parse('Just Eat serves the venue "{slug}"'))
def serves_venue(router, slug):
    serve_recorded_venue(router, slug)


@given(parsers.parse('Just Eat does not know the venue "{slug}"'))
def unknown_venue(router, slug):
    router.get(f"{CDN_BASE_URL}/{slug}_es_manifest.json").respond(404)


async def hang_forever(request):
    await asyncio.sleep(60)


@given(parsers.parse('Just Eat never answers for the venue "{slug}"'))
def never_answers(router, slug):
    router.get(f"{CDN_BASE_URL}/{slug}_es_manifest.json").mock(side_effect=hang_forever)


@given(parsers.parse("runs time out after {seconds} seconds"))
def run_timeout(monkeypatch, seconds):
    monkeypatch.setenv("CRAWLER_RUN_TIMEOUT_SECONDS", seconds)


@given(parsers.re(r'the URL list contains (?P<urls>".+")'))
def url_list(monkeypatch, urls):
    listed = json.loads(f"[{urls.replace('" and "', '", "')}]")
    monkeypatch.setattr("libs.crawler.processor.load_venue_urls", functools.partial(list, listed))


@when("I run the crawler")
def run_crawler(router, context):
    try:
        call_command("crawl_just_eat", output_dir=context["output_dir"], stdout=io.StringIO())
    except CommandError as error:
        context["exit_code"] = error.returncode
    else:
        context["exit_code"] = 0


@then("the command succeeds")
def succeeds(context):
    assert context["exit_code"] == 0


@then("the command reports failures")
def reports_failures(context):
    assert context["exit_code"] == 1


@then(parsers.parse('the output contains venue "{restaurant_id}" exactly as in just_eat_venue_example.json'))
def output_matches_example(context, restaurant_id):
    output = load_json(_run_dir(context) / "just_eat_venues.json")
    assert output[restaurant_id] == load_json(TIFLIS / "expected_venue.json")


@then(parsers.parse('the failures file lists "{url}"'))
def failures_list(context, url):
    failures = load_json(_run_dir(context) / "just_eat_venues.failures.json")
    assert list(failures) == [url]


@then("the command reports a timeout")
def reports_timeout(context):
    assert context["exit_code"] == 2


@then("no output file is created")
def no_output(context):
    assert not (_run_dir(context) / "just_eat_venues.json").exists()



@then("the database contains no venues")
def no_venues_in_database():
    assert not Venue.objects.exists()  # only a pipeline run publishes venues
