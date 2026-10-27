"""Every fixed value of the crawler: Just Eat endpoints, accepted values from its payloads, file names and sizes."""

import re

# --- Just Eat ------------------------------------------------------------------------------------------------

CDN_BASE_URL = "https://menu-globalmenucdn.justeat-int.com"
DYNAMIC_BASE_URL = "https://i18n.api.just-eat.io"
# Requests a venue makes at the same time once its manifest is read (items, details, rating, listing).
REQUESTS_PER_VENUE = 4
MAX_BACKOFF_SECONDS = 30  # cap of the exponential backoff between retries

# Values from the payloads that end up in request URLs; anything else could steer requests elsewhere.
CATALOGUE_FILE = re.compile(r"^[a-z0-9_-]+_es_[A-Za-z]+\.json$")
RESTAURANT_ID = re.compile(r"^\d{1,12}$")
POSTCODE = re.compile(r"^\d{5}$")
VENUE_URL_PATH = re.compile(r"^/restaurants-(?P<slug>[^/]+)/menu/?$")

# --- mapping to the output -----------------------------------------------------------------------------------

IMAGE_TRANSFORMATIONS = "ar_4:3,c_thumb,h_450,w_600/f_auto/q_auto"  # fixed Cloudinary transformations
DISH_PHOTO = re.compile(r"/v1/[a-z]{2}/dishes/")  # a real photo of the venue's dish (not a stock image)
AI_GENERATED_MARK = "t_jet_ai_watermark"

# --- files ---------------------------------------------------------------------------------------------------

ENV_PREFIX = "CRAWLER_"  # CRAWLER_BATCH_SIZE, CRAWLER_TIMEOUT_SECONDS...
OUTPUT_NAME = "just_eat_venues"
RUN_DIR_FORMAT = "%Y%m%dT%H%M%SZ"  # run folders are named after their start time, in UTC
MAX_RUN_DIR_ATTEMPTS = 1000  # -2, -3... suffixes tried when another run started in the same second
# On a folder shared with the host (Docker Desktop on a Mac) every write is a round trip: the 860 MB file of a
# full crawl took 53 minutes in 8 KB writes. In 8 MB chunks it is about a hundred writes.
WRITE_CHUNK_BYTES = 8 * 1024 * 1024
