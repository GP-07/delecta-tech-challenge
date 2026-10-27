"""Fixed values of the menus app: batch sizes, field lists and limits."""

from decimal import Decimal

from apps.pipeline.constants import CATEGORIZE_STEP, CRAWL_STEP, GOOGLE_LOAD_STEP, MATCH_STEP

OUTPUT_NAME = "menu_items.json"  # written to the run folder by the categorization
BATCH_SIZE = 1000  # menu items per INSERT / UPDATE
MENUS_PER_QUERY = 50  # venue menus are large (up to MBs each): only a few in memory at a time
MAX_ITEM_ID_LENGTH = 64  # item and menu ids, as stored
MAX_TEXT_LENGTH = 255  # section and item names, evidence, as stored
CENT = Decimal("0.01")  # prices are stored rounded to cents

CLASSIFICATION_FIELDS = ["category", "confidence", "method", "is_combo", "evidence", "classified_at"]
ITEM_FIELDS = ["menu_ids", "section", "name", "description", "price", "confidence", "method", "is_combo",
               "evidence", "classified_at"]
FIELDS_KEPT_BY_PEOPLE = ["category_id", "confidence", "method", "is_combo", "evidence"]  # of a manual correction

STEPS_BEFORE_PUBLISHING = [CRAWL_STEP, GOOGLE_LOAD_STEP, MATCH_STEP, CATEGORIZE_STEP]
PUBLISH_LOCK_ID = 7_360_001  # pg_advisory_xact_lock key: runs publish one at a time
