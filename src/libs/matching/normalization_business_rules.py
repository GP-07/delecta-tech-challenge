"""How names and addresses are read before comparing them. The vocabularies and thresholds are in constants.py.

Names
    tokens(name)                 the words of a name without joining words:
                                 'Restaurante La Tagliatella' -> ['restaurante', 'tagliatella']
Addresses
    split_street_and_number()    the first "street, number" of a free-text address:
                                 'CC Glòries, Av. Diagonal, 220, Sant Martí, 08018' -> ('Av. Diagonal', '220')
    street_key(street)           the street name without its type, joining words nor language:
                                 'Carrer del Consell de Cent' and 'Calle Consejo de Ciento' -> 'consell cent'
    are_same_street(a, b)        the same street despite spelling: abbreviated ('univ' / 'universitat') or with a
                                 small difference ('lepanto' / 'lepant')
"""

from rapidfuzz import fuzz

from libs.matching.constants import (
    MIN_ABBREVIATION_LENGTH,
    NUMBER_MARKER,
    SAME_STREET_SIMILARITY,
    STOPWORDS,
    STREET_ALIASES,
    STREET_AND_NUMBER,
    STREET_TYPES,
)
from libs.matching.text_helpers import normalize


def tokens(text: str | None) -> list[str]:
    """Normalised words, without joining words ('de', 'la', 'the'...)."""
    return [word for word in normalize(text).split() if word not in STOPWORDS]


def split_street_and_number(address: str | None) -> tuple[str, str | None]:
    """The first street followed by a 1-4 digit number; the whole text and no number when there is none.

    'Carrer de Pau Claris, 77' -> ('Carrer de Pau Claris', '77')
    'Calle Clot 49'            -> ('Calle Clot', '49')
    'Rambla nº 16'             -> ('Rambla', '16')   (the number marker is removed first)
    'Plaça Catalunya'          -> ('Plaça Catalunya', None)
    """
    found = STREET_AND_NUMBER.search(NUMBER_MARKER.sub("", address or ""))
    if not found:
        return address or "", None
    return found.group(1), found.group(2)


def street_key(street: str | None) -> str:
    """The words that name the street: no street type ('carrer', 'av'), no joining words, Spanish aliases in Catalan.

    'Avinguda Diagonal' -> 'diagonal';  'C/ de Pau Claris' -> 'pau claris';  'Consejo de Ciento' -> 'consell cent'
    """
    key = " ".join(word for word in normalize(street).split() if word not in STREET_TYPES and word not in STOPWORDS)
    return STREET_ALIASES.get(key, key)


def are_same_street(street_key_a: str, street_key_b: str) -> bool:
    """Two street keys name the same street, compared without spaces ('paral lel' = 'parallel'):
    one is an abbreviation of the other (at least MIN_ABBREVIATION_LENGTH letters), or they are similar enough
    (rapidfuzz ratio of at least SAME_STREET_SIMILARITY)."""
    joined_a, joined_b = street_key_a.replace(" ", ""), street_key_b.replace(" ", "")
    is_abbreviation = (min(len(joined_a), len(joined_b)) >= MIN_ABBREVIATION_LENGTH
                       and (joined_a.startswith(joined_b) or joined_b.startswith(joined_a)))
    return is_abbreviation or fuzz.ratio(joined_a, joined_b) >= SAME_STREET_SIMILARITY
