"""Fixed values of the pipeline: the names of its steps (as in settings.PIPELINE_STEPS) and its limits."""

CRAWL_STEP = "crawl_just_eat"
GOOGLE_LOAD_STEP = "load_google_venues"
MATCH_STEP = "match_venues"
CATEGORIZE_STEP = "categorize_menu_items"
PUBLISH_STEP = "publish_run"

MAX_ERROR_LENGTH = 2000  # characters of an error message kept in a step and its run
# A RUNNING step is only declared lost this long after its time limit: the worker may still be recording it.
STALLED_RUNNING_GRACE_SECONDS = 600
HASH_BLOCK_BYTES = 1024 * 1024  # input files are hashed (SHA-256) in blocks of this size
