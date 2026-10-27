"""Seeds src/crawler/data/brands.json ({uniqueName: brand}) from a reference venues dataset.

Usage: python -m libs.crawler.build_brands path/to/just_eat_venues.json [--output path]

Existing entries in the output file are kept (the reference file only adds or updates brands), so
manual additions survive a re-seed.
"""

import argparse
import json
from pathlib import Path

DEFAULT_OUTPUT = Path(__file__).resolve().parent / "data" / "brands.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("venues", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    venues = json.loads(args.venues.read_text(encoding="utf-8"))
    brands = json.loads(args.output.read_text(encoding="utf-8")) if args.output.exists() else {}
    brands.update({venue["uniqueName"]: venue["brand"] for venue in venues.values() if venue.get("brand")})

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(dict(sorted(brands.items())), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{len(brands)} brands written to {args.output}")


if __name__ == "__main__":
    main()
