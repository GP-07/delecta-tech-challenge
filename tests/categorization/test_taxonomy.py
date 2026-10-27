from pathlib import Path

import pytest
from openpyxl import Workbook

from libs.categorization import taxonomy as taxonomy_module
from libs.categorization.constants import TAXONOMY_HEADER
from libs.categorization.taxonomy import TaxonomyFileError, read_taxonomy

TAXONOMY = Path(__file__).parents[1] / "fixtures" / "categorization" / "food_categories.xlsx"
PIZZA = ("e403ed6ee7621f735892a3e1a2e40dd7e37b23f4", "food", "pizza", "pizza", "false")


def xlsx(path: Path, rows) -> Path:
    workbook = Workbook()
    for row in rows:
        workbook.active.append(list(row))
    workbook.save(path)
    return path


def test_the_taxonomy_file_is_read_with_its_101_categories():
    taxonomy = read_taxonomy(TAXONOMY)

    assert len(taxonomy) == 101
    pizza = taxonomy["pizza"]
    assert (pizza.uidentifier, pizza.family, pizza.parent, pizza.is_generic_or_other) == (PIZZA[0], "food", "pizza",
                                                                                          False)
    assert taxonomy["generic fish"].is_generic_or_other


def test_a_generic_category_knows_its_other_sibling():
    taxonomy = read_taxonomy(TAXONOMY)

    assert taxonomy.sibling(taxonomy["generic sweets"], "other").name == "other sweets"
    assert taxonomy.sibling(taxonomy["pizza"], "other") is None


def test_a_missing_file_is_rejected(tmp_path):
    with pytest.raises(TaxonomyFileError, match="not found"):
        read_taxonomy(tmp_path / "nope.xlsx")


def test_a_file_that_is_not_a_spreadsheet_is_rejected(tmp_path):
    path = tmp_path / "food_categories.xlsx"
    path.write_text("uidentifier,family,name")

    with pytest.raises(TaxonomyFileError, match="invalid"):
        read_taxonomy(path)


def test_unexpected_columns_are_rejected(tmp_path):
    with pytest.raises(TaxonomyFileError, match="expected columns"):
        read_taxonomy(xlsx(tmp_path / "t.xlsx", [("id", "name"), ("1", "pizza")]))


def test_a_single_invalid_row_rejects_the_whole_file(tmp_path):
    rows = [TAXONOMY_HEADER, PIZZA, ("not-a-sha1", "food", "burger", "fast food", "false")]

    with pytest.raises(TaxonomyFileError, match="row 3"):
        read_taxonomy(xlsx(tmp_path / "t.xlsx", rows))


def test_a_family_other_than_food_or_drink_is_rejected(tmp_path):
    rows = [TAXONOMY_HEADER, (PIZZA[0], "toys", "pizza", "pizza", "false")]

    with pytest.raises(TaxonomyFileError, match="row 2"):
        read_taxonomy(xlsx(tmp_path / "t.xlsx", rows))


def test_files_too_large_or_too_long_are_rejected(tmp_path, monkeypatch):
    beer = ("95befded05d6a7dd0aad9881392e177a8a0f7289", "drink", "beer", "beer", "false")
    path = xlsx(tmp_path / "t.xlsx", [TAXONOMY_HEADER, PIZZA, beer])
    monkeypatch.setattr(taxonomy_module, "TAXONOMY_MAX_ROWS", 1)
    with pytest.raises(TaxonomyFileError, match="more than 1 rows"):
        read_taxonomy(path)

    monkeypatch.setattr(taxonomy_module, "TAXONOMY_MAX_BYTES", 10)
    with pytest.raises(TaxonomyFileError, match="larger than"):
        read_taxonomy(path)
