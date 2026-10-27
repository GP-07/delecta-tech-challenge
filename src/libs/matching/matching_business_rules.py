"""When a Just Eat venue and a Google place are the same venue. The thresholds and weights are in constants.py.

Words of two names
    word_credit(word, other_words)        1 for the same word, a partial credit for a typo, 0 otherwise
    word_credits(words, other_words)      the credit of each word, also when written together or apart
    shares_only_area_words(...)           the names only share place names ("Diagonal Mar"): not similar at all
    has_distinctive_word(...)             a name has a distinctive word, shared or not with the other one
Two places
    distance_score(distance_m)            1 at the same point, 0.5 at HALF_DISTANCE_SCORE_M, towards 0 further away
    overall_score(...)                    name, distance and address in a single number, to rank candidates
    decision rules                        one function per rule; decision_rules() lists them in order
    decide(evidence)                      ACCEPTED, REVIEW or not a candidate: the first rule that applies
    ranking_key(match)                    the order in which candidates get their Google place (best first)
"""

from collections.abc import Callable

from rapidfuzz import fuzz

from libs.matching.constants import (
    AREA_WORDS,
    DISTANCE_SCORE_WEIGHT,
    HALF_DISTANCE_SCORE_M,
    NAME_SCORE_WEIGHT,
    NEARBY_M,
    REASON_DISTINCTIVE_NAME_FAR_AWAY,
    REASON_DISTINCTIVE_NAME_NEARBY,
    REASON_GENERIC_NAME_NEARBY,
    REASON_PARTLY_SIMILAR_NAME_NEARBY,
    REASON_SIMILAR_NAME_SAME_ADDRESS,
    SAME_ADDRESS_NEARBY_M,
    SAME_ADDRESS_WEIGHT,
    SIMILAR_NAME,
    STRONG_NAME,
    TYPO_MIN_LENGTH,
    TYPO_SIMILARITY,
)
from libs.matching.domain import Decision, Evidence, Match

# --- words of two names ------------------------------------------------------------------------------------


def word_credit(word: str, other_words: list[str]) -> float:
    """How much of `word` is in the other name.

    'goiko' in ['goiko', 'grill']   -> 1.0   the same word
    'napoli' in ['nappoli']         -> 0.92  a typo: the rapidfuzz ratio / 100, from TYPO_SIMILARITY (85)
    'bar' in ['bao']                -> 0.0   words shorter than TYPO_MIN_LENGTH must be the same
    'sushi' in ['pizza']            -> 0.0
    """
    if word in other_words:
        return 1.0
    if len(word) < TYPO_MIN_LENGTH:
        return 0.0
    best_similarity = max((fuzz.ratio(word, other_word) for other_word in other_words
                           if len(other_word) >= TYPO_MIN_LENGTH), default=0.0)
    return best_similarity / 100 if best_similarity >= TYPO_SIMILARITY else 0.0


def word_credits(words: list[str], other_words: list[str]) -> list[float]:
    """The credit of each word of a name in the other one, also when the names write it together or apart:

    ['mixiang'] in ['mi', 'xiang']  -> [1.0]       'mixiang' is 'mi' + 'xiang'
    ['mi', 'xiang'] in ['mixiang']  -> [1.0, 1.0]  'mi' + 'xiang' is 'mixiang'
    """
    joined_pairs = [first + second for first, second in zip(other_words, other_words[1:], strict=False)]
    credits = [word_credit(word, other_words + joined_pairs) for word in words]
    for position, (first, second) in enumerate(zip(words, words[1:], strict=False)):
        if first + second in other_words:
            credits[position] = credits[position + 1] = 1.0
    return credits


def shares_only_area_words(words: list[str], credits: list[float]) -> bool:
    """Every word the name shares with the other one is a place name (AREA_WORDS): "Starbucks Diagonal Mar" is
    not the "Diagonal Mar" shopping centre."""
    return all(credit == 0 or word in AREA_WORDS for word, credit in zip(words, credits, strict=True))


def has_distinctive_word(weights: list[float], credits: list[float], distinctive_weight: float, *,
                         shared: bool) -> bool:
    """A name has a distinctive word (weight at least `distinctive_weight`) that the other name has too
    (`shared=True`) or lacks (`shared=False`).

    Shared:  "Goiko Grill" / "Goiko": "goiko" is distinctive and shared, so the name is specific.
    Missing on both sides is a conflict: "Restaurante Chino Dao" / "Restaurante Chino Sabroso" each have a
    distinctive word the other lacks ("dao", "sabroso"): most likely two venues in the same building.
    """
    return any((credit > 0) == shared and weight >= distinctive_weight
               for weight, credit in zip(weights, credits, strict=True))


# --- two places --------------------------------------------------------------------------------------------


def distance_score(distance_m: float) -> float:
    """1 at the same point, 0.5 at HALF_DISTANCE_SCORE_M (40 m), ~0.14 at 100 m: 1 / (1 + (d / 40)²)."""
    return 1 / (1 + (distance_m / HALF_DISTANCE_SCORE_M) ** 2)


def overall_score(name_score: float, distance_m: float, same_address: bool) -> float:
    """0.6 name + 0.25 distance + 0.15 same address. Only ranks the candidates; `decide` uses the rules."""
    return (NAME_SCORE_WEIGHT * name_score + DISTANCE_SCORE_WEIGHT * distance_score(distance_m)
            + SAME_ADDRESS_WEIGHT * same_address)


def is_nearby(evidence: Evidence) -> bool:
    return evidence.distance_m <= NEARBY_M


# --- decision rules: each one (Evidence) -> (Decision, reason) or None when it does not apply --------------------


def distinctive_name_nearby(evidence: Evidence) -> tuple[Decision, str] | None:
    """ACCEPTED: a strong, distinctive name, nearby or at the same address ("Goiko Grill" / "GOIKO", 20 m)."""
    if (evidence.name_score >= STRONG_NAME and evidence.name_is_specific
            and (is_nearby(evidence) or evidence.same_address)):
        return Decision.ACCEPTED, REASON_DISTINCTIVE_NAME_NEARBY
    return None


def similar_name_at_same_address(evidence: Evidence) -> tuple[Decision, str] | None:
    """ACCEPTED: a partly similar name at the same street and number, very close. Not when only common words are
    shared and each name has its own distinctive word ("Restaurante Chino Dao" / "Restaurante Chino Sabroso" in the
    same building: most likely two different venues)."""
    if (evidence.name_score >= SIMILAR_NAME and evidence.same_address
            and evidence.distance_m <= SAME_ADDRESS_NEARBY_M
            and (evidence.name_is_specific or not evidence.name_conflict)):
        return Decision.ACCEPTED, REASON_SIMILAR_NAME_SAME_ADDRESS
    return None


def distinctive_name_far_away(evidence: Evidence) -> tuple[Decision, str] | None:
    """REVIEW: a strong, distinctive name, but beyond NEARBY_M (a pin misplaced, or another branch)."""
    if evidence.name_score >= STRONG_NAME and evidence.name_is_specific:
        return Decision.REVIEW, REASON_DISTINCTIVE_NAME_FAR_AWAY
    return None


def partly_similar_name_nearby(evidence: Evidence) -> tuple[Decision, str] | None:
    """REVIEW: a partly similar name sharing a distinctive word, nearby."""
    if evidence.name_score >= SIMILAR_NAME and evidence.name_is_specific and is_nearby(evidence):
        return Decision.REVIEW, REASON_PARTLY_SIMILAR_NAME_NEARBY
    return None


def generic_name_nearby(evidence: Evidence) -> tuple[Decision, str] | None:
    """REVIEW: a strong name made only of common words ("Pizzeria Napoli"), nearby."""
    if evidence.name_score >= STRONG_NAME and is_nearby(evidence):
        return Decision.REVIEW, REASON_GENERIC_NAME_NEARBY
    return None


DecisionRule = Callable[[Evidence], tuple[Decision, str] | None]


def decision_rules() -> tuple[DecisionRule, ...]:
    """The rules, in order: the first that applies decides. To add one, write a function (Evidence) -> (Decision,
    reason) | None and put it here at its place.

    | rule                          | name score | distinctive         | where                             | decision |
    |-------------------------------|------------|---------------------|-----------------------------------|----------|
    | distinctive_name_nearby       | >= 0.8     | yes                 | <= 150 m or same address          | ACCEPTED |
    | similar_name_at_same_address  | >= 0.5     | yes, or no conflict | same address and <= 100 m         | ACCEPTED |
    | distinctive_name_far_away     | >= 0.8     | yes                 | anywhere within the search radius | REVIEW   |
    | partly_similar_name_nearby    | >= 0.5     | yes                 | <= 150 m                          | REVIEW   |
    | generic_name_nearby           | >= 0.8     | no                  | <= 150 m                          | REVIEW   |
    | (none applies)                |            |                     |                                   | none     |

    A name alone never decides far away, and an address alone never decides at all (a shopping centre has dozens
    of venues at the same address).
    """
    return (distinctive_name_nearby, similar_name_at_same_address, distinctive_name_far_away,
            partly_similar_name_nearby, generic_name_nearby)


def decide(evidence: Evidence) -> tuple[Decision | None, str]:
    """The decision of the first rule that applies; (None, "") when none does: not a candidate."""
    for rule in decision_rules():
        decision = rule(evidence)
        if decision is not None:
            return decision
    return None, ""


def ranking_key(match: Match) -> tuple:
    """Accepted before review, then without a name conflict, then by overall score; the ids make the order
    deterministic. Candidates are assigned in this order, so the surest pairs take their Google place first."""
    return (match.decision != Decision.ACCEPTED, match.evidence.name_conflict, -match.evidence.score,
            match.source_id, match.target_id)
