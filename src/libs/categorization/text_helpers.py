"""Text cleaning of dish names, menu sections and descriptions, before looking for keywords."""

import unicodedata

from libs.categorization.constants import APOSTROPHES, NOT_TEXT


def normalize(text: str | None) -> str:
    """Lowercase ASCII words; '+' and ',' are kept as words of their own, since they separate a dish from its extras.

        'Pollo Asado + Coca-Cola, 33cl' -> 'pollo asado + coca cola , 33cl'
        'Dürüm Kebab & Patatas'          -> 'durum kebab and patatas'
    """
    ascii_text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    ascii_text = APOSTROPHES.sub("", ascii_text).replace("&", " and ").replace("+", " + ").replace(",", " , ")
    return " ".join(NOT_TEXT.sub(" ", ascii_text).split())


def words(text: str | None) -> list[str]:
    return normalize(text).split()
