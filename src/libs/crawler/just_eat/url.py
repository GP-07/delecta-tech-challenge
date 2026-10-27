"""Venue URL → slug.

URLs come from the curated src/crawler/data/just_eat_urls.json, so they are not validated beyond extracting
the slug. If the list ever becomes user-provided, validate them here (https, host www.just-eat.es only).
"""

from urllib.parse import urlsplit

from libs.crawler.constants import VENUE_URL_PATH


def slug_from_url(url: str) -> str:
    """https://www.just-eat.es/restaurants-{slug}/menu -> slug"""
    match = VENUE_URL_PATH.match(urlsplit(url).path)
    if not match:
        raise ValueError(f"Not a Just Eat venue URL: {url!r}")
    return match["slug"]
