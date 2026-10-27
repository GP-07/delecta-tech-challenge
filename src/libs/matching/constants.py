"""Every fixed value of the matching: vocabularies, thresholds and weights.

The logic that applies them is in normalization_business_rules.py (how names and addresses are read) and
matching_business_rules.py (when two places are the same venue). Thresholds were tuned on the 200 venues labelled by
hand (tests/fixtures/matching); changing one changes the measured precision and recall, which the tests check.
"""

import re

from libs.matching.domain import NameSimilarity

# --- geography -----------------------------------------------------------------------------------------

EARTH_RADIUS_M = 6_371_000
# Side of a cell of the search grid, in degrees: ~555 m of latitude and ~420 m of longitude in Barcelona (41.4° N),
# wider than any search radius used, so the 3 x 3 cells around a point always cover the whole circle.
GRID_CELL_DEGREES = 0.005
# A degree of latitude is ~111 km everywhere; a degree of longitude shrinks towards the poles. 80 km per degree is
# a safe lower bound for both up to ~44° N: a radius above GRID_CELL_DEGREES * 80 km would overflow the 3 x 3 cells.
MIN_METRES_PER_DEGREE = 80_000
# Row and column offsets of the 3 x 3 cells searched around a point: its own cell and the 8 around it.
GRID_NEIGHBOUR_OFFSETS = (-1, 0, 1)

# --- normalization of names and addresses (Spanish, Catalan and English as written in Barcelona) ------------------

# Joining words that say nothing about the venue.
STOPWORDS = frozenset({
    "a", "al", "and", "by", "d", "de", "del", "dels", "el", "els", "en", "i", "l", "la", "las", "les", "lo",
    "los", "of", "the", "y",
})
# Street types, in every spelling seen in the data ("Carrer", "Calle", "C/", "Av.", "Pg.", ...).
STREET_TYPES = frozenset({
    "av", "avda", "avenida", "avinguda", "c", "calle", "carrer", "carretera", "cl", "ctra", "gran", "pg",
    "passatge", "passeig", "paseo", "pasaje", "pl", "placa", "plaza", "ptge", "rambla", "rda", "ronda", "trav",
    "travessera", "via",
})
# Neighbourhoods, districts and shopping centres of the area. In a venue name they only say where the branch is
# ("Goiko Barcelona Laietana", "UDON Diagonal Mar"), so they weigh little when comparing names.
AREA_WORDS = frozenset({
    "andreu", "antoni", "arenas", "badalona", "barcelona", "barceloneta", "barris", "bcn", "besos", "bonanova",
    "born", "carmel", "cc", "center", "centre", "centro", "ciutat", "clot", "comercial", "corts", "diagonal", "drago",
    "eixample", "fort", "franca", "gervasi", "glories", "gotic", "gotico", "gracia", "guinardo", "horta",
    "hospitalet", "hostafrancs", "illa", "maquinista", "mar", "maremagnum", "marti", "montjuic", "multiespai", "nou",
    "olimpica", "pedralbes", "pienc", "poble", "poblenou", "provencals", "putxet", "raval", "sagrada", "sagrera",
    "sant", "sants", "sarria", "shopping", "som", "triangle", "trinitat", "vallcarca", "vella", "verneda",
    "westfield", "zona",
})
# Spanish names of streets too different from the Catalan ones for a fuzzy comparison (seen in the data).
STREET_ALIASES = {"consejo ciento": "consell cent"}

APOSTROPHES = re.compile(r"[’'´`]")
NOT_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")
# "<street>, <number>" or "<street> <number>"; 1-4 digits so a postcode (08004) is never a street number.
STREET_AND_NUMBER = re.compile(r"([^,\d]*[^\W\d][^,\d]*?)[,\s]+(\d{1,4})(?!\d)")
# "n 16", "nº 16", "num. 16": the number marker would otherwise be read as the street name.
NUMBER_MARKER = re.compile(r"\b(?:n|no|num|numero)\.?\s*(?=\d)", re.IGNORECASE)

# Two street names are the same street from this rapidfuzz ratio (0-100): "lepanto" ~ "lepant",
# "paral lel" ~ "parallel".
SAME_STREET_SIMILARITY = 80
# A street written as the start of the other one is an abbreviation from this length: "univ" for "universitat".
MIN_ABBREVIATION_LENGTH = 3

# --- name similarity ---------------------------------------------------------------------------------------

# Two words are the same word with a typo from this rapidfuzz ratio (0-100): "napoli" ~ "nappoli",
# "basilico" ~ "basilisco". Shorter words must match exactly ("bar" is not "bao").
TYPO_SIMILARITY = 85
TYPO_MIN_LENGTH = 4
# Words of the address or the area weigh a quarter: in "Popeyes Josep Tarradellas" only "popeyes" names the venue.
LOCATION_WORD_WEIGHT = 0.25
# A word found in at most 0.2% of the Google names (~44 of 21,926) is distinctive by itself ("goiko", "tiflis").
DISTINCTIVE_WORD_SHARE = 0.002

NOT_SIMILAR = NameSimilarity(score=0.0, specific=False, conflict=False)  # names without words to compare

# --- decision ----------------------------------------------------------------------------------------------

# Candidates are looked for within this distance: 99% of the clear matches are within 250 m; shopping centres
# (one address for the whole building, the pin anywhere in it) need a bit more.
SEARCH_RADIUS_M = 400
NEARBY_M = 150  # close enough for a strong name to decide on its own
SAME_ADDRESS_NEARBY_M = 100  # close enough for a similar name at the same street and number
STRONG_NAME = 0.8  # name score from which the names are the same name
SIMILAR_NAME = 0.5  # name score from which the names are partly the same

# Reasons stored with each link (shown and filtered in the admin), one per decision rule.
REASON_DISTINCTIVE_NAME_NEARBY = "distinctive name nearby"
REASON_SIMILAR_NAME_SAME_ADDRESS = "similar name at the same address"
REASON_DISTINCTIVE_NAME_FAR_AWAY = "distinctive name, but far away"
REASON_PARTLY_SIMILAR_NAME_NEARBY = "partly similar name nearby"
REASON_GENERIC_NAME_NEARBY = "similar but generic name nearby"

# Overall score, only used to rank the candidates (the decision uses the rules, not this number).
NAME_SCORE_WEIGHT = 0.6
DISTANCE_SCORE_WEIGHT = 0.25
SAME_ADDRESS_WEIGHT = 0.15
# Distance at which the distance score is 0.5: 1 at the same point, 0.5 at 40 m, ~0.14 at 100 m.
HALF_DISTANCE_SCORE_M = 40
