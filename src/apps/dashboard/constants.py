"""Fixed values of the dashboard: who may see it, the accepted query parameters and the buckets of its charts."""

from apps.venues.choices import MatchGroup
from libs.categorization.constants import LOW_CONFIDENCE

MATCH_GROUPS = MatchGroup.values  # accepted, confirmed, review, rejected, unmatched
DISH_GROUPS = [MatchGroup.ACCEPTED, MatchGroup.CONFIRMED]  # only matched venues have categorized dishes
LEVELS = ["parent", "name"]  # of the taxonomy: group ("pizza") or category ("calzone")
FAMILIES = ["food", "drink"]
ORDERS = ["venues", "items"]
TOP_ROWS = 10  # dishes and restaurants listed in a category's detail
PAGE_SIZE = 25  # rows per page of the venue and dish lists

# (label, from, up to - excluded; None: no limit)
CONFIDENCE_BUCKETS = [("< 0,4", 0, 0.4), ("0,4 – 0,6", 0.4, LOW_CONFIDENCE), ("0,6 – 0,8", LOW_CONFIDENCE, 0.8),
                      ("≥ 0,8", 0.8, None)]

# Read access a user needs to see the dashboard (the "Dashboard" group of migration 0001 has exactly these).
DASHBOARD_PERMISSIONS = [
    "pipeline.view_pipelinerun",
    "venues.view_venue",
    "venues.view_venuematch",
    "menus.view_menuitem",
    "menus.view_foodcategory",
]
LOCKED_MESSAGE = "Demasiados intentos fallidos. Probá de nuevo en unos minutos."
