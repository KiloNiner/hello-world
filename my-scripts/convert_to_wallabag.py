#!/usr/bin/env python3
"""Convert Matter history CSV export to Wallabag-compatible JSON import format."""

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

INPUT_FILE = Path(__file__).parent / "_matter_history.csv"
OUTPUT_FILE = Path(__file__).parent / "wallabag_import.json"


def parse_date(date_str: str) -> str | None:
    """Convert '2022-05-22 14:47:50' to ISO 8601 with UTC offset."""
    date_str = date_str.strip()
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        return dt.isoformat()
    except ValueError:
        print(f"  Warning: could not parse date '{date_str}', omitting.", file=sys.stderr)
        return None


def convert():
    entries = []
    skipped = 0

    with open(INPUT_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row["URL"].strip()
            if not url:
                skipped += 1
                continue

            # Tags: single value per row in this export (no comma-splitting needed)
            tags = [row["Tags"].strip()] if row["Tags"].strip() else []

            # Read=True → archived; Read takes precedence over In Queue for ambiguous items
            is_archived = 1 if row["Read"].strip() == "True" else 0
            is_starred = 1 if row["Favorited"].strip() == "True" else 0

            entry = {
                "url": url,
                "title": row["Title"].strip(),
                "is_archived": is_archived,
                "is_starred": is_starred,
                "tags": tags,
                "created_at": parse_date(row["Last Interaction Date"]),
            }

            # Drop None created_at to keep JSON clean
            if entry["created_at"] is None:
                del entry["created_at"]

            entries.append(entry)

    archived = sum(1 for e in entries if e["is_archived"])
    unread = len(entries) - archived

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    print(f"Converted {len(entries)} entries → {OUTPUT_FILE}")
    print(f"  Archived (read):  {archived}")
    print(f"  Unread:           {unread}")
    if skipped:
        print(f"  Skipped (no URL): {skipped}")


if __name__ == "__main__":
    convert()
