import os
from dataclasses import dataclass, fields

from libs.crawler.constants import ENV_PREFIX


@dataclass(frozen=True, slots=True)
class CrawlerSettings:
    """Crawler tuning. Defaults are deliberately polite towards Just Eat; override via CRAWLER_* env vars."""

    # Venues crawled at the same time (one batch). Each venue makes 4-5 requests to Just Eat. Measured on the full
    # list: 10 took 6.2 minutes (4 took 12.1), with the same failures and no request refused by Just Eat.
    batch_size: int = 10
    run_timeout_seconds: float = 3600.0  # a whole run taking longer is cancelled and fails
    request_delay_seconds: float = 0.25  # pause before every request
    timeout_seconds: float = 20.0
    max_retries: int = 4  # attempts per request, including the first
    backoff_seconds: float = 1.0  # base of the exponential backoff between retries
    max_response_bytes: int = 30 * 1024 * 1024
    user_agent: str = "delectatech-challenge-crawler/0.1 (+https://github.com/; data pipeline technical test)"

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "CrawlerSettings":
        environ = os.environ if environ is None else environ
        overrides = {}
        for setting in fields(cls):
            value = environ.get(f"{ENV_PREFIX}{setting.name.upper()}")
            if value is not None:
                overrides[setting.name] = type(setting.default)(value)
        return cls(**overrides)
