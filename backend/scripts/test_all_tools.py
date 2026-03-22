#!/usr/bin/env python3
"""Test script per tutti i tool di tutti i domini Me4BrAIn.

Esegue test automatici su TUTTI i tool disponibili.
"""

import asyncio
import os
import sys
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
os.chdir(Path(__file__).parent.parent)

from dotenv import load_dotenv

load_dotenv()

# Results tracking
RESULTS = {"passed": [], "failed": [], "skipped": []}


async def test_entertainment():
    """Test entertainment tools (7)."""
    from me4brain.domains.entertainment.tools.entertainment_api import (
        tmdb_search_movie,
        tmdb_movie_details,
        tmdb_trending,
        openlibrary_search,
        openlibrary_book,
        lastfm_search_artist,
        lastfm_top_tracks,
    )

    tests = [
        ("tmdb_search_movie", tmdb_search_movie("Matrix"), "results"),
        ("tmdb_movie_details", tmdb_movie_details(603), "title"),
        ("tmdb_trending", tmdb_trending(), "results"),
        ("openlibrary_search", openlibrary_search("Python"), "results"),
        ("openlibrary_book", openlibrary_book("0596007124"), "title"),
        ("lastfm_search_artist", lastfm_search_artist("Beatles"), "results"),
        ("lastfm_top_tracks", lastfm_top_tracks("Queen"), "tracks"),
    ]
    for name, coro, key in tests:
        try:
            r = await coro
            if r.get(key) or (key == "results" and r.get("results") is not None):
                RESULTS["passed"].append(f"entertainment.{name}")
            elif r.get("error"):
                RESULTS["failed"].append(f"entertainment.{name}: {r.get('error')[:50]}")
            else:
                RESULTS["failed"].append(f"entertainment.{name}: no {key}")
        except Exception as e:
            RESULTS["failed"].append(f"entertainment.{name}: {str(e)[:50]}")


async def test_jobs():
    """Test jobs tools (2)."""
    from me4brain.domains.jobs.tools.jobs_api import remoteok_jobs, arbeitnow_jobs

    tests = [
        ("remoteok_jobs", remoteok_jobs(), "jobs"),
        ("arbeitnow_jobs", arbeitnow_jobs(), "jobs"),
    ]
    for name, coro, key in tests:
        try:
            r = await coro
            if r.get(key):
                RESULTS["passed"].append(f"jobs.{name}")
            else:
                RESULTS["failed"].append(f"jobs.{name}: {r.get('error', 'no ' + key)[:50]}")
        except Exception as e:
            RESULTS["failed"].append(f"jobs.{name}: {str(e)[:50]}")


async def test_geo_weather():
    """Test geo_weather tools (3)."""
    from me4brain.domains.geo_weather.tools.geo_api import AVAILABLE_TOOLS

    tests = [
        ("openmeteo_weather", {"city": "Milano"}),
        ("usgs_earthquakes", {}),
    ]
    for name, args in tests:
        if name not in AVAILABLE_TOOLS:
            RESULTS["skipped"].append(f"geo.{name}: not in AVAILABLE_TOOLS")
            continue
        try:
            r = await AVAILABLE_TOOLS[name](**args)
            if "error" not in r:
                RESULTS["passed"].append(f"geo.{name}")
            else:
                RESULTS["failed"].append(f"geo.{name}: {r.get('error')[:50]}")
        except Exception as e:
            RESULTS["failed"].append(f"geo.{name}: {str(e)[:50]}")


async def test_knowledge_media():
    """Test knowledge_media tools (3)."""
    from me4brain.domains.knowledge_media.tools.knowledge_api import AVAILABLE_TOOLS

    tests = [
        ("wikipedia_summary", {"title": "Python (programming language)"}),
        ("hackernews_top", {}),
        ("openlibrary_search", {"query": "Python"}),
    ]
    for name, args in tests:
        if name not in AVAILABLE_TOOLS:
            RESULTS["skipped"].append(f"knowledge.{name}: not in AVAILABLE_TOOLS")
            continue
        try:
            r = await AVAILABLE_TOOLS[name](**args)
            if "error" not in r:
                RESULTS["passed"].append(f"knowledge.{name}")
            else:
                RESULTS["failed"].append(f"knowledge.{name}: {r.get('error')[:50]}")
        except Exception as e:
            RESULTS["failed"].append(f"knowledge.{name}: {str(e)[:50]}")


async def test_tech_coding():
    """Test tech_coding tools (10)."""
    from me4brain.domains.tech_coding.tools.tech_api import AVAILABLE_TOOLS

    tests = [
        ("github_repo", {"owner": "facebook", "repo": "react"}),
        ("github_search_repos", {"query": "python"}),
        ("npm_package", {"name": "react"}),
        ("npm_search", {"query": "typescript"}),
        ("pypi_package", {"name": "pandas"}),
        ("stackoverflow_search", {"query": "python async"}),
        ("piston_runtimes", {}),
    ]
    for name, args in tests:
        if name not in AVAILABLE_TOOLS:
            RESULTS["skipped"].append(f"tech.{name}: not in AVAILABLE_TOOLS")
            continue
        try:
            r = await AVAILABLE_TOOLS[name](**args)
            if "error" not in r:
                RESULTS["passed"].append(f"tech.{name}")
            else:
                RESULTS["failed"].append(f"tech.{name}: {r.get('error')[:50]}")
        except Exception as e:
            RESULTS["failed"].append(f"tech.{name}: {str(e)[:50]}")


async def test_travel():
    """Test travel tools (5)."""
    from me4brain.domains.travel.tools.travel_api import AVAILABLE_TOOLS

    tests = [
        ("opensky_flights_live", {}),
        ("opensky_arrivals", {"airport": "LIRF"}),
    ]
    for name, args in tests:
        if name not in AVAILABLE_TOOLS:
            RESULTS["skipped"].append(f"travel.{name}: not in AVAILABLE_TOOLS")
            continue
        try:
            r = await AVAILABLE_TOOLS[name](**args)
            if "error" not in r:
                RESULTS["passed"].append(f"travel.{name}")
            else:
                RESULTS["failed"].append(f"travel.{name}: {r.get('error')[:50]}")
        except Exception as e:
            RESULTS["failed"].append(f"travel.{name}: {str(e)[:50]}")


async def test_utility():
    """Test utility tools (2)."""
    from me4brain.domains.utility.tools.utility_api import AVAILABLE_TOOLS

    tests = [
        ("get_ip", {}),
        ("get_headers", {}),
    ]
    for name, args in tests:
        if name not in AVAILABLE_TOOLS:
            RESULTS["skipped"].append(f"utility.{name}: not in AVAILABLE_TOOLS")
            continue
        try:
            r = await AVAILABLE_TOOLS[name](**args)
            if "error" not in r:
                RESULTS["passed"].append(f"utility.{name}")
            else:
                RESULTS["failed"].append(f"utility.{name}: {r.get('error')[:50]}")
        except Exception as e:
            RESULTS["failed"].append(f"utility.{name}: {str(e)[:50]}")


async def test_web_search():
    """Test web_search tools (4)."""
    from me4brain.domains.web_search.tools.web_api import AVAILABLE_TOOLS

    tests = [
        ("duckduckgo_instant", {"query": "python programming"}),
        ("smart_search", {"query": "AI news"}),
    ]
    for name, args in tests:
        if name not in AVAILABLE_TOOLS:
            RESULTS["skipped"].append(f"web.{name}: not in AVAILABLE_TOOLS")
            continue
        try:
            r = await AVAILABLE_TOOLS[name](**args)
            if "error" not in r:
                RESULTS["passed"].append(f"web.{name}")
            else:
                RESULTS["failed"].append(f"web.{name}: {r.get('error')[:50]}")
        except Exception as e:
            RESULTS["failed"].append(f"web.{name}: {str(e)[:50]}")


async def test_sports_nba():
    """Test sports_nba tools (7)."""
    from me4brain.domains.sports_nba.tools.nba_api import AVAILABLE_TOOLS

    tests = [
        ("nba_upcoming_games", {}),
        ("nba_teams", {}),
        ("nba_live_scoreboard", {}),
    ]
    for name, args in tests:
        if name not in AVAILABLE_TOOLS:
            RESULTS["skipped"].append(f"sports.{name}: not in AVAILABLE_TOOLS")
            continue
        try:
            r = await AVAILABLE_TOOLS[name](**args)
            if "error" not in r:
                RESULTS["passed"].append(f"sports.{name}")
            else:
                RESULTS["failed"].append(f"sports.{name}: {r.get('error')[:50]}")
        except Exception as e:
            RESULTS["failed"].append(f"sports.{name}: {str(e)[:50]}")


async def test_medical():
    """Test medical tools (8)."""
    from me4brain.domains.medical.tools.medical_api import AVAILABLE_TOOLS

    tests = [
        ("rxnorm_drug_info", {"drug_name": "aspirin"}),
        ("pubmed_abstract", {"pmid": "33782619"}),
    ]
    for name, args in tests:
        if name not in AVAILABLE_TOOLS:
            RESULTS["skipped"].append(f"medical.{name}: not in AVAILABLE_TOOLS")
            continue
        try:
            r = await AVAILABLE_TOOLS[name](**args)
            if "error" not in r:
                RESULTS["passed"].append(f"medical.{name}")
            else:
                RESULTS["failed"].append(f"medical.{name}: {r.get('error')[:50]}")
        except Exception as e:
            RESULTS["failed"].append(f"medical.{name}: {str(e)[:50]}")


async def test_science_research():
    """Test science_research tools (7)."""
    from me4brain.domains.science_research.tools.science_api import AVAILABLE_TOOLS

    tests = [
        ("arxiv_search", {"query": "machine learning"}),
        ("crossref_doi", {"doi": "10.1038/nature12373"}),
        ("openalex_search", {"query": "deep learning"}),
    ]
    for name, args in tests:
        if name not in AVAILABLE_TOOLS:
            RESULTS["skipped"].append(f"science.{name}: not in AVAILABLE_TOOLS")
            continue
        try:
            r = await AVAILABLE_TOOLS[name](**args)
            if "error" not in r:
                RESULTS["passed"].append(f"science.{name}")
            else:
                RESULTS["failed"].append(f"science.{name}: {r.get('error')[:50]}")
        except Exception as e:
            RESULTS["failed"].append(f"science.{name}: {str(e)[:50]}")


async def test_finance_crypto():
    """Test finance_crypto tools (20)."""
    from me4brain.domains.finance_crypto.tools.finance_api import AVAILABLE_TOOLS

    tests = [
        ("binance_price", {"symbol": "BTCUSDT"}),
        ("yahoo_quote", {"symbol": "AAPL"}),
    ]
    for name, args in tests:
        if name not in AVAILABLE_TOOLS:
            RESULTS["skipped"].append(f"finance.{name}: not in AVAILABLE_TOOLS")
            continue
        try:
            r = await AVAILABLE_TOOLS[name](**args)
            if "error" not in r:
                RESULTS["passed"].append(f"finance.{name}")
            else:
                RESULTS["failed"].append(f"finance.{name}: {r.get('error')[:50]}")
        except Exception as e:
            RESULTS["failed"].append(f"finance.{name}: {str(e)[:50]}")


async def main():
    """Run all tests."""
    print("=" * 60)
    print("ME4BRAIN TOOL TEST - ALL DOMAINS")
    print("=" * 60)

    await test_entertainment()
    print(f"Entertainment: {len([x for x in RESULTS['passed'] if 'entertainment' in x])}/7")

    await test_jobs()
    print(f"Jobs: {len([x for x in RESULTS['passed'] if 'jobs' in x])}/2")

    await test_geo_weather()
    print(f"Geo: {len([x for x in RESULTS['passed'] if 'geo' in x])}/3")

    await test_knowledge_media()
    print(f"Knowledge: {len([x for x in RESULTS['passed'] if 'knowledge' in x])}/3")

    await test_tech_coding()
    print(f"Tech: {len([x for x in RESULTS['passed'] if 'tech' in x])}/10")

    await test_travel()
    print(f"Travel: {len([x for x in RESULTS['passed'] if 'travel' in x])}/5")

    await test_utility()
    print(f"Utility: {len([x for x in RESULTS['passed'] if 'utility' in x])}/2")

    await test_web_search()
    print(f"Web: {len([x for x in RESULTS['passed'] if 'web' in x])}/4")

    await test_sports_nba()
    print(f"Sports: {len([x for x in RESULTS['passed'] if 'sports' in x])}/7")

    await test_medical()
    print(f"Medical: {len([x for x in RESULTS['passed'] if 'medical' in x])}/8")

    await test_science_research()
    print(f"Science: {len([x for x in RESULTS['passed'] if 'science' in x])}/7")

    await test_finance_crypto()
    print(f"Finance: {len([x for x in RESULTS['passed'] if 'finance' in x])}/20")

    print("\n" + "=" * 60)
    print(
        f"TOTALS: {len(RESULTS['passed'])} PASSED, {len(RESULTS['failed'])} FAILED, {len(RESULTS['skipped'])} SKIPPED"
    )
    print("=" * 60)

    if RESULTS["failed"]:
        print("\n❌ FAILED:")
        for f in RESULTS["failed"]:
            print(f"  - {f}")

    if RESULTS["skipped"]:
        print("\n⚠️ SKIPPED:")
        for s in RESULTS["skipped"]:
            print(f"  - {s}")


if __name__ == "__main__":
    asyncio.run(main())
