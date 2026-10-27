"""Brand lookup by venue uniqueName.

Just Eat does not expose the brand (corporate group) in any public payload we found, and it cannot be
inferred from the venue name ("Pans & Company" -> "Eat Out"). It is therefore reference data, kept in a
JSON file that can be extended over time. The shipped file was seeded from just_eat_venues.json.
"""

import json
from collections.abc import Mapping
from importlib import resources
from pathlib import Path


class BrandResolver:
    def __init__(self, mapping: Mapping[str, str]) -> None:
        self._mapping = dict(mapping)

    @classmethod
    def from_file(cls, path: Path) -> "BrandResolver":
        return cls(_validated(json.loads(Path(path).read_text(encoding="utf-8"))))

    @classmethod
    def default(cls) -> "BrandResolver":
        content = resources.files("libs.crawler.data").joinpath("brands.json").read_text(encoding="utf-8")
        return cls(_validated(json.loads(content)))

    def resolve(self, unique_name: str) -> str | None:
        return self._mapping.get(unique_name)

    def __len__(self) -> int:
        return len(self._mapping)


def _validated(data: object) -> dict[str, str]:
    if not isinstance(data, dict) or not all(
        isinstance(key, str) and key and isinstance(value, str) and value for key, value in data.items()
    ):
        raise ValueError("brands file must be a JSON object of {uniqueName: brand} non-empty strings")
    return data
