#!/usr/bin/env python3
"""Test E2E per tool Me4BrAIn via pipeline LLM.

NOTA: Richiede from __future__ import annotations per Python 3.9 compatibility.

3 Livelli di test:
- L1: Singolo tool, query naturali (119 test)
- L2: Multi-tool, stesso dominio (25 test)
- L3: Cross-analysis, domini diversi (15 test)

Usage:
    python scripts/test_llm_e2e.py --level L1 --smoke      # Solo 1 query per dominio
    python scripts/test_llm_e2e.py --level L1 --all        # Tutti i 119 test
    python scripts/test_llm_e2e.py --level L2              # Multi-tool tests
    python scripts/test_llm_e2e.py --level L3              # Cross-analysis tests
    python scripts/test_llm_e2e.py --all-levels            # Tutti i livelli
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional, List, Dict

import httpx

# =============================================================================
# Configuration
# =============================================================================

API_BASE = "http://localhost:8089"
TIMEOUT = 60.0  # Timeout per query LLM
DELAY_BETWEEN_QUERIES = 1.0  # Delay per evitare rate limiting

# =============================================================================
# Test Cases L1: Singolo Tool
# =============================================================================

L1_TESTS: dict[str, list[dict[str, Any]]] = {
    "finance_crypto": [
        {
            "query": "Quanto sta il BTC adesso? Voglio vedere se è il momento di comprare",
            "expected_tool": "coingecko_price",
            "validation": {"field": "price", "type": "exists"},
        },
        {
            "query": "Mi fai vedere cosa sta andando forte nel mondo crypto?",
            "expected_tool": "coingecko_trending",
            "validation": {"field": "coins", "type": "exists"},
        },
        {
            "query": "Fammi vedere l'andamento di ETH nell'ultimo periodo",
            "expected_tool": "coingecko_chart",
            "validation": {"field": "prices", "type": "exists"},
        },
        {
            "query": "Su Binance a quanto sta scambiando il Bitcoin?",
            "expected_tool": "binance_price",
            "validation": {"field": "price", "type": "exists"},
        },
        {
            "query": "Quant'è il volume di trading nelle ultime 24 ore su BTC?",
            "expected_tool": "binance_ticker_24h",
            "validation": {"field": "volume", "type": "exists"},
        },
        {
            "query": "Come sta andando Apple in borsa oggi?",
            "expected_tool": "yahoo_quote",
            "validation": {"field": "regularMarketPrice", "type": "exists"},
        },
        {
            "query": "Dammi una quotazione aggiornata su Microsoft",
            "expected_tool": "finnhub_quote",
            "validation": {"field": "c", "type": "exists"},
        },
        {
            "query": "Cosa si dice sui mercati finanziari? Ci sono news importanti?",
            "expected_tool": "finnhub_news",
            "validation": {"field": "headline", "type": "exists"},
        },
        {
            "query": "Mi serve il dato del PIL americano dell'ultimo anno",
            "expected_tool": "fred_series",
            "validation": {"field": "observations", "type": "exists"},
        },
        {
            "query": "Devo trovare i filing SEC di Apple, quelli 10-K",
            "expected_tool": "edgar_filings",
            "validation": {"field": "filings", "type": "exists"},
        },
    ],
    "google_workspace": [
        {
            # File creato: "Report Budget Q1 2026" nella cartella _me4brain_e2e_test
            "query": "Trova il documento Report Budget Q1 che ho salvato, devo vedere i numeri",
            "expected_tool": "google_drive_search",
            "validation": {"field": "files", "type": "exists"},
        },
        {
            "query": "Cosa ho di recente sul Drive? Fammi vedere gli ultimi file",
            "expected_tool": "google_drive_list_files",
            "validation": {"field": "files", "type": "exists"},
        },
        {
            # Evento calendario creato: "Riunione Test Me4BrAIn" domani alle 15
            "query": "Cosa ho in agenda domani? C'è qualche riunione?",
            "expected_tool": "google_calendar_upcoming",
            "validation": {"field": "events", "type": "exists"},
        },
        {
            # Sheet creato: "Vendite 2026" con dati da Gennaio ad Aprile
            "query": "Aprimi lo spreadsheet Vendite 2026 e dimmi i numeri del Q1",
            "expected_tool": "google_sheets_get_values",
            "validation": {"field": "values", "type": "exists"},
        },
    ],
    "geo_weather": [
        {
            "query": "Che tempo fa fuori? Devo uscire e non so se prendere l'ombrello",
            "expected_tool": "openmeteo_weather",
            "validation": {"field": "temperature", "type": "exists"},
        },
        {
            "query": "Ci sono stati terremoti recenti in zona Italia?",
            "expected_tool": "usgs_earthquakes",
            "validation": {"field": "features", "type": "exists"},
        },
        {
            "query": "Quando sono le prossime feste? Sto pianificando le vacanze 2026",
            "expected_tool": "nager_holidays",
            "validation": {"field": "holidays", "type": "exists"},
        },
    ],
    "science_research": [
        {
            "query": "Sto cercando paper su machine learning, qualcosa di recente",
            "expected_tool": "arxiv_search",
            "validation": {"field": "papers", "type": "exists"},
        },
        {
            "query": "Trova info su questo DOI 10.1038/s41586-023",
            "expected_tool": "crossref_doi",
            "validation": {"field": "title", "type": "exists"},
        },
        {
            "query": "Ricerche accademiche su intelligenza artificiale, cosa c'è di nuovo?",
            "expected_tool": "openalex_search",
            "validation": {"field": "results", "type": "exists"},
        },
        {
            "query": "Paper sulla architettura transformer, pubblicazioni recenti",
            "expected_tool": "semanticscholar_search",
            "validation": {"field": "data", "type": "exists"},
        },
    ],
    "entertainment": [
        {
            "query": "Quel film con DiCaprio sui sogni, come si chiamava?",
            "expected_tool": "tmdb_search_movie",
            "validation": {"field": "results", "type": "exists"},
        },
        {
            "query": "Cosa c'è di nuovo al cinema? Film popolari del momento",
            "expected_tool": "tmdb_trending",
            "validation": {"field": "results", "type": "exists"},
        },
        {
            "query": "Trova i Beatles su Last.fm, voglio info sulla band",
            "expected_tool": "lastfm_search_artist",
            "validation": {"field": "artist", "type": "exists"},
        },
    ],
    "food": [
        {
            "query": "Come si fa la carbonara? Ingredienti e procedimento",
            "expected_tool": "mealdb_search",
            "validation": {"field": "meals", "type": "exists"},
        },
        {
            "query": "Suggeriscimi una ricetta a caso, non so cosa cucinare",
            "expected_tool": "mealdb_random",
            "validation": {"field": "meals", "type": "exists"},
        },
        {
            "query": "Ho dei pomodori in frigo, cosa posso farci?",
            "expected_tool": "mealdb_by_ingredient",
            "validation": {"field": "meals", "type": "exists"},
        },
    ],
    "tech_coding": [
        {
            "query": "Info sul repository TensorFlow, quanto è popolare?",
            "expected_tool": "github_repo",
            "validation": {"field": "stargazers_count", "type": "exists"},
        },
        {
            "query": "Ci sono issue aperti su PyTorch da risolvere?",
            "expected_tool": "github_issues",
            "validation": {"field": "items", "type": "exists"},
        },
        {
            "query": "Quanto pesa il package React su npm?",
            "expected_tool": "npm_package",
            "validation": {"field": "name", "type": "exists"},
        },
        {
            "query": "Info su pandas, versione corrente e dipendenze",
            "expected_tool": "pypi_package",
            "validation": {"field": "info", "type": "exists"},
        },
    ],
    "web_search": [
        {
            "query": "Qual è la capitale della Francia? Rispondimi veloce",
            "expected_tool": "duckduckgo_instant",
            "validation": {"field": "abstract", "type": "exists"},
        },
        {
            "query": "Ricerca approfondita sulle novità AI nel 2026",
            "expected_tool": "tavily_search",
            "validation": {"field": "results", "type": "exists"},
        },
    ],
    "medical": [
        {
            "query": "Info sul farmaco ibuprofene, dosaggio e controindicazioni",
            "expected_tool": "rxnorm_drug_info",
            "validation": {"field": "name", "type": "exists"},
        },
        {
            "query": "Ricerca articoli su COVID-19 vaccine efficacy",
            "expected_tool": "pubmed_search",
            "validation": {"field": "results", "type": "exists"},
        },
    ],
    "travel": [
        {
            "query": "Ci sono voli sopra Milano in questo momento?",
            "expected_tool": "opensky_flights_live",
            "validation": {"field": "states", "type": "exists"},
        },
        {
            "query": "Traccia il volo con call sign RYR4913",
            "expected_tool": "adsb_aircraft_by_callsign",
            "validation": {"field": "aircraft", "type": "exists"},
        },
    ],
    "jobs": [
        {
            "query": "Cerco lavoro remoto come Python developer",
            "expected_tool": "remoteok_jobs",
            "validation": {"field": "jobs", "type": "exists"},
        },
        {
            "query": "Lavori in Europa per sviluppatori?",
            "expected_tool": "arbeitnow_jobs",
            "validation": {"field": "jobs", "type": "exists"},
        },
    ],
    "utility": [
        {
            "query": "Qual è il mio indirizzo IP pubblico?",
            "expected_tool": "get_ip",
            "validation": {"field": "ip", "type": "exists"},
        },
    ],
    "knowledge_media": [
        {
            "query": "Raccontami brevemente la storia dell'Impero Romano",
            "expected_tool": "wikipedia_summary",
            "validation": {"field": "extract", "type": "exists"},
        },
        {
            "query": "Cosa c'è di interessante su HackerNews oggi?",
            "expected_tool": "hackernews_top",
            "validation": {"field": "stories", "type": "exists"},
        },
    ],
}

# =============================================================================
# Test Cases L2: Multi-Tool (Stesso Dominio)
# =============================================================================

L2_TESTS: list[dict[str, Any]] = [
    {
        "query": "Dammi prezzo BTC e ETH insieme, voglio confrontarli",
        "expected_tools": ["coingecko_price"],
        "min_tools": 1,
        "domain": "finance",
    },
    {
        "query": "Come stanno Apple e Microsoft? Confronto rapido in borsa",
        "expected_tools": ["yahoo_quote", "finnhub_quote"],
        "min_tools": 1,
        "domain": "finance",
    },
    {
        "query": "Cerca il file budget su Drive e dimmi cosa contiene",
        "expected_tools": ["google_drive_search", "google_drive_get_content"],
        "min_tools": 1,
        "domain": "google",
    },
    {
        "query": "Meteo Roma e Milano, devo decidere dove andare nel weekend",
        "expected_tools": ["openmeteo_weather"],
        "min_tools": 1,
        "domain": "geo",
    },
    {
        "query": "Cerca paper su BERT e dammi anche le citazioni del più importante",
        "expected_tools": ["arxiv_search", "semanticscholar_citations"],
        "min_tools": 1,
        "domain": "science",
    },
    {
        "query": "Film di Nolan, elencameli tutti",
        "expected_tools": ["tmdb_search_movie"],
        "min_tools": 1,
        "domain": "entertainment",
    },
    {
        "query": "Repository ML su GitHub più popolari e mostra issues",
        "expected_tools": ["github_search_repos", "github_issues"],
        "min_tools": 1,
        "domain": "tech",
    },
    {
        "query": "Ricetta pasta al pesto e calorie del pesto",
        "expected_tools": ["mealdb_search", "openfoodfacts_search"],
        "min_tools": 1,
        "domain": "food",
    },
]

# =============================================================================
# Test Cases L3: Cross-Analysis (Domini Diversi)
# =============================================================================

L3_TESTS: list[dict[str, Any]] = [
    {
        "query": "Devo viaggiare a Milano domani. Che tempo fa lì e ci sono voli?",
        "expected_domains": ["geo_weather", "travel"],
        "min_tools": 2,
    },
    {
        "query": "Prezzo Bitcoin e paper recenti su blockchain, voglio fare un articolo",
        "expected_domains": ["finance_crypto", "science_research"],
        "min_tools": 2,
    },
    {
        "query": "Quotazione Tesla e ultime news sul settore automotive",
        "expected_domains": ["finance_crypto", "web_search"],
        "min_tools": 2,
    },
    {
        "query": "Eventi in calendario questa settimana e che tempo farà",
        "expected_domains": ["google_workspace", "geo_weather"],
        "min_tools": 2,
    },
    {
        "query": "Film trending oggi e suggeriscimi una ricetta per movie night",
        "expected_domains": ["entertainment", "food"],
        "min_tools": 2,
    },
    {
        "query": "Paper su nutrizione e ricette salutari con verdure",
        "expected_domains": ["medical", "food"],
        "min_tools": 2,
    },
    {
        "query": "Lavori Python remoto e repos GitHub correlati",
        "expected_domains": ["jobs", "tech_coding"],
        "min_tools": 2,
    },
    {
        "query": "Crypto trending e news su regolamentazione crypto",
        "expected_domains": ["finance_crypto", "web_search"],
        "min_tools": 2,
    },
]


# =============================================================================
# Test Result Types
# =============================================================================


@dataclass
class TestResult:
    """Risultato singolo test."""

    query: str
    expected_tool: str | None = None
    expected_tools: list[str] | None = None
    actual_tools: list[str] = field(default_factory=list)
    passed: bool = False
    error: str | None = None
    response_preview: str = ""
    latency_ms: float = 0.0
    level: str = "L1"


@dataclass
class TestSummary:
    """Riepilogo test suite."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    results: list[TestResult] = field(default_factory=list)


# =============================================================================
# Test Execution
# =============================================================================


async def execute_query(query: str) -> dict[str, Any]:
    """Esegue query via API /v1/memory/query/stream (cognitive_pipeline).

    Usa endpoint streaming che passa per cognitive_pipeline.py
    invece di tool_agent.py (keyword matching).
    """
    tools_used = []
    analysis = {}
    response_content = ""

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async with client.stream(
            "POST",
            f"{API_BASE}/v1/memory/query/stream",
            json={"query": query},
            headers={"X-Tenant-ID": "test", "X-User-ID": "e2e-test"},
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        chunk_type = data.get("chunk_type", "")

                        if chunk_type == "analysis":
                            analysis = data.get("analysis", {})
                        elif chunk_type == "tool":
                            tool_call = data.get("tool_call", {})
                            tool_name = tool_call.get("tool", "")
                            if tool_name and tool_call.get("success"):
                                tools_used.append({"tool_name": tool_name})
                        elif chunk_type == "content":
                            response_content += data.get("content", "")
                    except json.JSONDecodeError:
                        pass

    return {
        "tools_used": tools_used,
        "analysis": analysis,
        "response": response_content,
        "domains_required": analysis.get("domains_required", []),
    }


def extract_tools_used(response: dict[str, Any]) -> list[str]:
    """Estrae nomi tool usati dalla risposta."""
    tools = []
    for tool in response.get("tools_used", []):
        if isinstance(tool, dict):
            tools.append(tool.get("tool_name", "unknown"))
        elif isinstance(tool, str):
            tools.append(tool)
    return tools


async def run_l1_test(test_case: dict[str, Any], domain: str) -> TestResult:
    """Esegue singolo test L1."""
    query = test_case["query"]
    expected = test_case["expected_tool"]
    start = time.time()

    result = TestResult(
        query=query,
        expected_tool=expected,
        level="L1",
    )

    try:
        response = await execute_query(query)
        latency = (time.time() - start) * 1000

        tools_used = extract_tools_used(response)
        result.actual_tools = tools_used
        result.latency_ms = latency
        result.response_preview = response.get("response", "")[:200]

        # Verifica: tool atteso è tra quelli utilizzati
        if expected in tools_used:
            result.passed = True
        elif len(tools_used) > 0:
            # Almeno un tool è stato chiamato
            result.error = f"Expected {expected}, got {tools_used}"
        else:
            result.error = "No tools used"

    except Exception as e:
        result.error = str(e)

    return result


async def run_l2_test(test_case: dict[str, Any]) -> TestResult:
    """Esegue singolo test L2 (multi-tool)."""
    query = test_case["query"]
    expected_tools = test_case["expected_tools"]
    min_tools = test_case.get("min_tools", 1)
    start = time.time()

    result = TestResult(
        query=query,
        expected_tools=expected_tools,
        level="L2",
    )

    try:
        response = await execute_query(query)
        latency = (time.time() - start) * 1000

        tools_used = extract_tools_used(response)
        result.actual_tools = tools_used
        result.latency_ms = latency
        result.response_preview = response.get("response", "")[:200]

        # Verifica: almeno min_tools usati, almeno uno degli expected
        if len(tools_used) >= min_tools:
            matches = [t for t in expected_tools if t in tools_used]
            if len(matches) > 0:
                result.passed = True
            else:
                result.error = f"No expected tools found. Got: {tools_used}"
        else:
            result.error = f"Only {len(tools_used)} tools used, expected {min_tools}+"

    except Exception as e:
        result.error = str(e)

    return result


async def run_l3_test(test_case: dict[str, Any]) -> TestResult:
    """Esegue singolo test L3 (cross-analysis)."""
    query = test_case["query"]
    expected_domains = test_case["expected_domains"]
    min_tools = test_case.get("min_tools", 2)
    start = time.time()

    result = TestResult(
        query=query,
        expected_tools=expected_domains,  # Riusa campo per domini
        level="L3",
    )

    try:
        response = await execute_query(query)
        latency = (time.time() - start) * 1000

        tools_used = extract_tools_used(response)
        result.actual_tools = tools_used
        result.latency_ms = latency
        result.response_preview = response.get("response", "")[:200]

        # Verifica: almeno min_tools usati
        if len(tools_used) >= min_tools:
            result.passed = True
        elif len(tools_used) > 0:
            result.error = f"Only {len(tools_used)} tools, expected {min_tools}+ for cross-analysis"
        else:
            result.error = "No tools used"

    except Exception as e:
        result.error = str(e)

    return result


# =============================================================================
# Test Runners
# =============================================================================


async def run_l1_smoke(verbose: bool = True) -> TestSummary:
    """Esegue 1 test per dominio (smoke test)."""
    summary = TestSummary()

    for domain, tests in L1_TESTS.items():
        if not tests:
            continue

        test = tests[0]  # Primo test di ogni dominio
        if verbose:
            print(f"\n🔍 [{domain}] {test['query'][:50]}...")

        result = await run_l1_test(test, domain)
        summary.results.append(result)
        summary.total += 1

        if result.passed:
            summary.passed += 1
            if verbose:
                print(f"   ✅ Tool: {result.actual_tools} ({result.latency_ms:.0f}ms)")
        elif result.error:
            summary.errors += 1
            if verbose:
                print(f"   ❌ Error: {result.error}")
        else:
            summary.failed += 1
            if verbose:
                print(f"   ⚠️ Wrong tool: {result.actual_tools}")

        await asyncio.sleep(DELAY_BETWEEN_QUERIES)

    return summary


async def run_l1_all(verbose: bool = True) -> TestSummary:
    """Esegue tutti i test L1."""
    summary = TestSummary()

    for domain, tests in L1_TESTS.items():
        if verbose:
            print(f"\n📦 Domain: {domain} ({len(tests)} tests)")

        for test in tests:
            if verbose:
                print(f"   🔍 {test['query'][:40]}...")

            result = await run_l1_test(test, domain)
            summary.results.append(result)
            summary.total += 1

            if result.passed:
                summary.passed += 1
                if verbose:
                    print(f"      ✅ {result.actual_tools} ({result.latency_ms:.0f}ms)")
            elif result.error:
                summary.errors += 1
                if verbose:
                    print(f"      ❌ {result.error}")
            else:
                summary.failed += 1

            await asyncio.sleep(DELAY_BETWEEN_QUERIES)

    return summary


async def run_l2_tests(verbose: bool = True) -> TestSummary:
    """Esegue test L2 multi-tool."""
    summary = TestSummary()

    if verbose:
        print(f"\n📦 L2: Multi-Tool Tests ({len(L2_TESTS)} tests)")

    for test in L2_TESTS:
        if verbose:
            print(f"   🔍 {test['query'][:50]}...")

        result = await run_l2_test(test)
        summary.results.append(result)
        summary.total += 1

        if result.passed:
            summary.passed += 1
            if verbose:
                print(f"      ✅ Tools: {result.actual_tools} ({result.latency_ms:.0f}ms)")
        else:
            summary.failed += 1
            if verbose:
                print(f"      ❌ {result.error}")

        await asyncio.sleep(DELAY_BETWEEN_QUERIES)

    return summary


async def run_l3_tests(verbose: bool = True) -> TestSummary:
    """Esegue test L3 cross-analysis."""
    summary = TestSummary()

    if verbose:
        print(f"\n📦 L3: Cross-Analysis Tests ({len(L3_TESTS)} tests)")

    for test in L3_TESTS:
        if verbose:
            print(f"   🔍 {test['query'][:50]}...")

        result = await run_l3_test(test)
        summary.results.append(result)
        summary.total += 1

        if result.passed:
            summary.passed += 1
            if verbose:
                print(f"      ✅ Tools: {result.actual_tools} ({result.latency_ms:.0f}ms)")
        else:
            summary.failed += 1
            if verbose:
                print(f"      ❌ {result.error}")

        await asyncio.sleep(DELAY_BETWEEN_QUERIES)

    return summary


# =============================================================================
# Report Generation
# =============================================================================


def print_summary(summaries: dict[str, TestSummary]) -> None:
    """Stampa riepilogo finale."""
    print("\n" + "=" * 60)
    print("📊 RIEPILOGO TEST E2E LLM")
    print("=" * 60)

    total_all = sum(s.total for s in summaries.values())
    passed_all = sum(s.passed for s in summaries.values())

    for level, summary in summaries.items():
        rate = (summary.passed / summary.total * 100) if summary.total > 0 else 0
        status = "✅" if rate >= 80 else "⚠️" if rate >= 60 else "❌"
        print(f"{status} {level}: {summary.passed}/{summary.total} ({rate:.1f}%)")

    print("-" * 60)
    overall_rate = (passed_all / total_all * 100) if total_all > 0 else 0
    print(f"📈 TOTALE: {passed_all}/{total_all} ({overall_rate:.1f}%)")


def generate_json_report(summaries: dict[str, TestSummary], output_path: str) -> None:
    """Genera report JSON."""
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "summaries": {},
    }

    for level, summary in summaries.items():
        report["summaries"][level] = {
            "total": summary.total,
            "passed": summary.passed,
            "failed": summary.failed,
            "errors": summary.errors,
            "pass_rate": (summary.passed / summary.total * 100) if summary.total > 0 else 0,
            "results": [
                {
                    "query": r.query[:100],
                    "expected": r.expected_tool or r.expected_tools,
                    "actual": r.actual_tools,
                    "passed": r.passed,
                    "error": r.error,
                    "latency_ms": r.latency_ms,
                }
                for r in summary.results
            ],
        }

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n📄 Report salvato: {output_path}")


# =============================================================================
# Main
# =============================================================================


async def main():
    parser = argparse.ArgumentParser(
        description="Test E2E Tool via Pipeline LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--level",
        choices=["L1", "L2", "L3"],
        default="L1",
        help="Livello di test da eseguire",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Solo smoke test (1 per dominio)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Esegui tutti i test del livello",
    )
    parser.add_argument(
        "--all-levels",
        action="store_true",
        help="Esegui tutti i livelli",
    )
    parser.add_argument(
        "--report",
        choices=["json", "none"],
        default="none",
        help="Formato report output",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Output minimo",
    )

    args = parser.parse_args()
    verbose = not args.quiet
    summaries: dict[str, TestSummary] = {}

    print("=" * 60)
    print("🧪 ME4BRAIN E2E TEST SUITE - Pipeline LLM")
    print("=" * 60)

    if args.all_levels:
        # Tutti i livelli
        summaries["L1"] = await run_l1_all(verbose)
        summaries["L2"] = await run_l2_tests(verbose)
        summaries["L3"] = await run_l3_tests(verbose)
    elif args.level == "L1":
        if args.smoke:
            summaries["L1-smoke"] = await run_l1_smoke(verbose)
        else:
            summaries["L1"] = await run_l1_all(verbose)
    elif args.level == "L2":
        summaries["L2"] = await run_l2_tests(verbose)
    elif args.level == "L3":
        summaries["L3"] = await run_l3_tests(verbose)

    print_summary(summaries)

    if args.report == "json":
        generate_json_report(summaries, "test_llm_e2e_report.json")

    # Exit code
    total = sum(s.total for s in summaries.values())
    passed = sum(s.passed for s in summaries.values())
    if total > 0 and (passed / total) < 0.70:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
