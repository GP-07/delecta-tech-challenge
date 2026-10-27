from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class Place:
    """A venue as the matcher sees it: whatever the source, only what both sources share."""

    id: str
    name: str
    address: str
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class NameSimilarity:
    score: float  # 0-1
    specific: bool  # the names share at least one distinctive word ("goiko"), not only common ones ("chino")
    conflict: bool  # each name has a distinctive word the other lacks ("Starbucks Hotel X" / "Vibra Hotel X")


class Decision(StrEnum):
    ACCEPTED = "ACCEPTED"  # linked automatically
    REVIEW = "REVIEW"  # plausible but not certain: a person confirms or rejects it


@dataclass(frozen=True, slots=True)
class Evidence:
    """Why two places look like the same venue; every score is between 0 and 1."""

    name_score: float
    name_is_specific: bool  # the shared words are distinctive, not just "restaurante" or "sushi"
    name_conflict: bool  # each name has a distinctive word the other lacks: possibly two venues in one building
    distance_m: float
    same_address: bool
    score: float  # overall, used to rank the candidates

    def as_dict(self) -> dict:
        return {
            "name_score": round(self.name_score, 3),
            "name_is_specific": self.name_is_specific,
            "name_conflict": self.name_conflict,
            "distance_m": round(self.distance_m, 1),
            "same_address": self.same_address,
            "score": round(self.score, 3),
        }


@dataclass(frozen=True, slots=True)
class Match:
    source_id: str  # Just Eat
    target_id: str  # Google
    decision: Decision
    reason: str
    evidence: Evidence = field(compare=False)
