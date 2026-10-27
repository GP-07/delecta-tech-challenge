import pytest

from libs.matching.address import Address
from libs.matching.normalization_business_rules import tokens
from libs.matching.text_helpers import normalize


@pytest.mark.parametrize(("raw", "expected"), [
    ("Pans & Company", "pans and company"),
    ("Dürüm Kebab Gràcia", "durum kebab gracia"),
    ("McDonald's", "mcdonalds"),
    ("Dori-Dori MDM", "dori dori mdm"),
    ("SHAJO | Sushi | Ramen", "shajo sushi ramen"),
    (None, ""),
])
def test_normalize(raw, expected):
    assert normalize(raw) == expected


def test_tokens_drop_joining_words():
    assert tokens("La Leggenda di Napoli y el Mar") == ["leggenda", "di", "napoli", "mar"]


@pytest.mark.parametrize(("raw", "street", "number"), [
    ("Carrer de Pau Claris, 77", "pau claris", "77"),
    ("Calle Clot 49", "clot", "49"),
    ("CC Glòries, Av. Diagonal, 220, Sant Martí, 08018 Barcelona", "diagonal", "220"),
    ("Carrer d'Olzinelles, n 16, Sants-Montjuïc, 08014 Barcelona", "dolzinelles", "16"),
    ("Pl. dels Països Catalans, s/n, Sants-Montjuïc, 08014 Barcelona", None, None),  # no street number
])
def test_parse_address(raw, street, number):
    address = Address.parse(raw)

    assert address.number == number
    if street:
        assert address.street == street


@pytest.mark.parametrize(("first", "second"), [
    ("Calle Lepanto 315", "Carrer de Lepant, 315, Eixample"),  # Spanish / Catalan
    ("Av. del Para?lel, 139", "Avinguda del Paral·lel, 139"),  # broken character in the source
    ("Ronda de la Universitat, 7", "Ronda de la Univ., 7, Eixample"),  # abbreviation
    ("Paseo de Sant Joan 58", "Pg. de St. Joan, 58, Eixample"),
    ("Calle Consejo de Ciento 211", "Carrer del Consell de Cent, 211, Eixample"),  # translated street name
])
def test_same_address_despite_spelling(first, second):
    assert Address.parse(first).same_as(Address.parse(second))


@pytest.mark.parametrize(("first", "second"), [
    ("Carrer de Casp, 48", "Carrer de Casp, 70"),  # same street, another number
    ("Carrer de Múrcia, 2", "Avinguda Meridiana, 194"),
    ("Pl. dels Països Catalans, s/n", "Pl. dels Països Catalans, s/n"),  # without numbers nothing is certain
])
def test_different_addresses(first, second):
    assert not Address.parse(first).same_as(Address.parse(second))
