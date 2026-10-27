import pytest

from libs.crawler.just_eat.url import slug_from_url


@pytest.mark.parametrize(
    ("url", "slug"),
    [
        ("https://www.just-eat.es/restaurants-tiflis-restaurant-barcelona/menu", "tiflis-restaurant-barcelona"),
        ("https://www.just-eat.es/restaurants-edo/menu/", "edo"),
        ("https://www.just-eat.es/restaurants-dona_tota-poblenou-barcelona/menu", "dona_tota-poblenou-barcelona"),
        ("https://www.just-eat.es/restaurants-supermercado-dia---numancia-barcelona/menu",
         "supermercado-dia---numancia-barcelona"),
    ],
)
def test_extracts_the_slug(url, slug):
    assert slug_from_url(url) == slug


@pytest.mark.parametrize("url", ["https://www.just-eat.es/area/08013", ""])
def test_rejects_urls_that_are_not_venue_pages(url):
    with pytest.raises(ValueError):
        slug_from_url(url)
