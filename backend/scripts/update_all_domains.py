#!/usr/bin/env python3
"""Bulk update ALL tool domains across all domain files."""

import re
import os

# DOMAIN MAPPINGS by file
MAPPINGS = {
    # Finance - già ok come "finance", rinominiamo solo
    "src/me4brain/domains/finance_crypto/tools/finance_api.py": {"finance_crypto": "finance"},
    # Entertainment - già ok
    "src/me4brain/domains/entertainment/tools/entertainment_api.py": {
        # No changes needed - entertainment stays entertainment
    },
    # Food - già ok
    "src/me4brain/domains/food/tools/food_api.py": {
        # No changes - food stays food
    },
    # Geo/Weather -> weather_geo
    "src/me4brain/domains/geo_weather/tools/geo_api.py": {"geo_weather": "weather_geo"},
    # Jobs - già ok
    "src/me4brain/domains/jobs/tools/jobs_api.py": {
        # No changes - jobs stays jobs
    },
    # Knowledge/Media -> search (for search tools) or entertainment (for media)
    "src/me4brain/domains/knowledge_media/tools/knowledge_api.py": {
        "knowledge_media": "search"  # wiki, openlibrary are search tools
    },
    # Medical - già ok
    "src/me4brain/domains/medical/tools/medical_api.py": {
        # No changes - medical stays medical
    },
    # Science Research -> science
    "src/me4brain/domains/science_research/tools/science_api.py": {"science_research": "science"},
    # Sports Booking -> sports
    "src/me4brain/domains/sports_booking/tools/playtomic_api.py": {"sports_booking": "sports"},
    # Sports NBA -> sports
    "src/me4brain/domains/sports_nba/tools/nba_api.py": {"sports_nba": "sports"},
    # Tech Coding -> dev_tools
    "src/me4brain/domains/tech_coding/tools/tech_api.py": {"tech_coding": "dev_tools"},
}


def update_file(filepath: str, domain_map: dict) -> int:
    """Update domains in a single file. Returns count of changes."""
    if not os.path.exists(filepath):
        print(f"SKIP: {filepath} not found")
        return 0

    if not domain_map:
        print(f"SKIP: {filepath} - no changes needed")
        return 0

    with open(filepath, "r") as f:
        content = f.read()

    changes = 0
    for old_domain, new_domain in domain_map.items():
        pattern = f'domain="{old_domain}"'
        replacement = f'domain="{new_domain}"'
        count = content.count(pattern)
        if count > 0:
            content = content.replace(pattern, replacement)
            changes += count
            print(f"  {old_domain} -> {new_domain}: {count} tools")

    if changes > 0:
        with open(filepath, "w") as f:
            f.write(content)

    return changes


def main():
    total_changes = 0
    for filepath, domain_map in MAPPINGS.items():
        print(f"\n{filepath}:")
        changes = update_file(filepath, domain_map)
        total_changes += changes

    print(f"\n{'=' * 50}")
    print(f"TOTAL: {total_changes} tools updated")


if __name__ == "__main__":
    main()
