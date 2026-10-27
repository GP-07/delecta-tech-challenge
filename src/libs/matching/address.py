from dataclasses import dataclass

from libs.matching.normalization_business_rules import are_same_street, split_street_and_number, street_key


@dataclass(frozen=True, slots=True)
class Address:
    """A street and number read from a free-text address, ready to compare (see normalization_business_rules)."""

    street: str  # street key: normalised, without street type nor joining words ("consell cent")
    number: str | None

    @classmethod
    def parse(cls, text: str | None) -> "Address":
        street, number = split_street_and_number(text)
        return cls(street=street_key(street), number=number)

    def same_as(self, other: "Address") -> bool:
        """Same number and same street. Without a street or a number on both sides it is never the same: a
        shopping centre gives the same street to dozens of venues."""
        if not (self.street and other.street and self.number and other.number):
            return False
        return self.number == other.number and are_same_street(self.street, other.street)
