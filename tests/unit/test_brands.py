import json

import pytest

from libs.crawler.brands import BrandResolver


def test_resolves_brand_by_unique_name():
    resolver = BrandResolver({"mcdonalds-sagrada-familia-barcelona": "McDonalds"})

    assert resolver.resolve("mcdonalds-sagrada-familia-barcelona") == "McDonalds"
    assert resolver.resolve("tiflis-restaurant-barcelona") is None


def test_loads_mapping_from_json_file(tmp_path):
    path = tmp_path / "brands.json"
    path.write_text(json.dumps({"vipslamaquinista": "GRUPO ALSEA"}), encoding="utf-8")

    assert BrandResolver.from_file(path).resolve("vipslamaquinista") == "GRUPO ALSEA"


def test_default_mapping_ships_with_the_package():
    resolver = BrandResolver.default()

    assert resolver.resolve("mcdonalds-sagrada-familia-barcelona") == "McDonalds"
    assert resolver.resolve("pans-and-company-can-drago-barcelona") == "Eat Out"
    assert len(resolver) == 654


@pytest.mark.parametrize("content", ['["a list"]', '{"slug": 1}', '{"": "x"}'])
def test_rejects_malformed_mapping(tmp_path, content):
    path = tmp_path / "brands.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError):
        BrandResolver.from_file(path)
