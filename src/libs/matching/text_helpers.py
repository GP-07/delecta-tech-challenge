"""Generic text cleaning, the first step before any rule reads a name or an address."""

import unicodedata

from libs.matching.constants import APOSTROPHES, NOT_ALPHANUMERIC


def normalize(text: str | None) -> str:
    """Lowercase ASCII words separated by single spaces.

        'Pans & Company'      -> 'pans and company'   ('&' is the word 'and')
        'Dürüm Kebab Gràcia'  -> 'durum kebab gracia' (accents removed: NFKD splits 'à' into 'a' + accent)
        "L'Antic Forn"        -> 'lantic forn'         (apostrophes joined, as people type it either way)
        'C/ Balmes, 129-131'  -> 'c balmes 129 131'    (any other symbol is a word break)
    """
    ascii_text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    ascii_text = APOSTROPHES.sub("", ascii_text).replace("&", " and ")
    return " ".join(NOT_ALPHANUMERIC.sub(" ", ascii_text).split())
