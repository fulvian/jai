#!/usr/bin/env python3
"""Test script per Tool Calling Engine API.

Testa gli endpoint:
- GET /v1/engine/stats
- GET /v1/engine/tools
- POST /v1/engine/call
- POST /v1/engine/query

Usage:
    python scripts/test_engine_api.py [--base-url http://localhost:8000]
"""

import argparse
import asyncio
import httpx
import json
import sys
from typing import Any


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def print_header(text: str) -> None:
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(60)}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}\n")


def print_success(text: str) -> None:
    print(f"{Colors.GREEN}✅ {text}{Colors.RESET}")


def print_error(text: str) -> None:
    print(f"{Colors.RED}❌ {text}{Colors.RESET}")


def print_info(text: str) -> None:
    print(f"{Colors.YELLOW}ℹ️  {text}{Colors.RESET}")


async def test_stats(client: httpx.AsyncClient) -> bool:
    """Test GET /v1/engine/stats"""
    print_header("Test: GET /v1/engine/stats")

    try:
        response = await client.get("/v1/engine/stats")

        if response.status_code == 200:
            data = response.json()
            print_success(f"Stats received - Total tools: {data['total_tools']}")
            print("\nDomini:")
            for domain in data["domains"][:5]:  # Show first 5
                print(f"  • {domain['domain']}: {domain['tool_count']} tools")
            if len(data["domains"]) > 5:
                print(f"  ... e altri {len(data['domains']) - 5} domini")
            return True
        else:
            print_error(f"Status {response.status_code}: {response.text}")
            return False

    except Exception as e:
        print_error(f"Exception: {e}")
        return False


async def test_list_tools(client: httpx.AsyncClient) -> bool:
    """Test GET /v1/engine/tools"""
    print_header("Test: GET /v1/engine/tools")

    try:
        response = await client.get("/v1/engine/tools")

        if response.status_code == 200:
            data = response.json()
            print_success(f"Tools list - Total: {data['total']}")
            print(f"\nDomini disponibili: {', '.join(data['domains'][:5])}")
            print("\nPrimi 5 tools:")
            for tool in data["tools"][:5]:
                print(f"  • {tool['name']}: {tool['description'][:50]}...")
            return True
        else:
            print_error(f"Status {response.status_code}: {response.text}")
            return False

    except Exception as e:
        print_error(f"Exception: {e}")
        return False


async def test_list_tools_filtered(client: httpx.AsyncClient) -> bool:
    """Test GET /v1/engine/tools con filtro"""
    print_header("Test: GET /v1/engine/tools?domain=finance_crypto")

    try:
        response = await client.get("/v1/engine/tools", params={"domain": "finance_crypto"})

        if response.status_code == 200:
            data = response.json()
            print_success(f"Filtered tools - Count: {data['total']}")
            for tool in data["tools"][:5]:
                print(f"  • {tool['name']}")
            return True
        else:
            print_error(f"Status {response.status_code}: {response.text}")
            return False

    except Exception as e:
        print_error(f"Exception: {e}")
        return False


async def test_get_tool(client: httpx.AsyncClient) -> bool:
    """Test GET /v1/engine/tools/{name}"""
    print_header("Test: GET /v1/engine/tools/coingecko_price")

    try:
        response = await client.get("/v1/engine/tools/coingecko_price")

        if response.status_code == 200:
            data = response.json()
            print_success(f"Tool found: {data['name']}")
            print(f"  Domain: {data['domain']}")
            print(f"  Description: {data['description'][:80]}...")
            print(f"  Parameters: {list(data['parameters'].keys())}")
            return True
        else:
            print_error(f"Status {response.status_code}: {response.text}")
            return False

    except Exception as e:
        print_error(f"Exception: {e}")
        return False


async def test_call_tool(client: httpx.AsyncClient) -> bool:
    """Test POST /v1/engine/call"""
    print_header("Test: POST /v1/engine/call")

    try:
        payload = {
            "tool_name": "coingecko_price",
            "arguments": {"ids": "bitcoin", "vs_currencies": "usd"},
        }
        print_info(f"Calling: {payload['tool_name']} with {payload['arguments']}")

        response = await client.post("/v1/engine/call", json=payload)

        if response.status_code == 200:
            data = response.json()
            if data["success"]:
                print_success(f"Tool executed in {data['latency_ms']:.0f}ms")
                if data["result"]:
                    # Show preview of result
                    result_str = json.dumps(data["result"], indent=2)[:200]
                    print(f"\nResult preview:\n{result_str}...")
            else:
                print_error(f"Tool failed: {data['error']}")
            return data["success"]
        else:
            print_error(f"Status {response.status_code}: {response.text}")
            return False

    except Exception as e:
        print_error(f"Exception: {e}")
        return False


async def test_query(client: httpx.AsyncClient) -> bool:
    """Test POST /v1/engine/query"""
    print_header("Test: POST /v1/engine/query")

    try:
        payload = {
            "query": "Qual è il prezzo attuale del Bitcoin?",
            "include_raw_results": True,
        }
        print_info(f"Query: {payload['query']}")

        response = await client.post("/v1/engine/query", json=payload, timeout=60)

        if response.status_code == 200:
            data = response.json()
            print_success(f"Query completed in {data['total_latency_ms']:.0f}ms")
            print(f"\nTools chiamati: {len(data['tools_called'])}")
            for tool in data["tools_called"]:
                status = "✅" if tool["success"] else "❌"
                print(f"  {status} {tool['tool_name']} ({tool['latency_ms']:.0f}ms)")

            print(f"\n{Colors.BOLD}Risposta:{Colors.RESET}")
            # Wrap answer
            answer = data["answer"]
            if len(answer) > 300:
                print(answer[:300] + "...")
            else:
                print(answer)
            return True
        else:
            print_error(f"Status {response.status_code}: {response.text}")
            return False

    except Exception as e:
        print_error(f"Exception: {e}")
        return False


async def run_tests(base_url: str) -> int:
    """Run all tests."""
    print_header("Tool Calling Engine API Tests")
    print(f"Base URL: {base_url}\n")

    results = []

    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        # Test order: from simpler to complex
        results.append(("Stats", await test_stats(client)))
        results.append(("List Tools", await test_list_tools(client)))
        results.append(("Filter Tools", await test_list_tools_filtered(client)))
        results.append(("Get Tool", await test_get_tool(client)))
        results.append(("Call Tool", await test_call_tool(client)))
        results.append(("Query", await test_query(client)))

    # Summary
    print_header("Test Summary")
    passed = sum(1 for _, r in results if r)
    failed = len(results) - passed

    for name, success in results:
        status = (
            f"{Colors.GREEN}PASS{Colors.RESET}" if success else f"{Colors.RED}FAIL{Colors.RESET}"
        )
        print(f"  {name:20} {status}")

    print(f"\n{Colors.BOLD}Total: {passed}/{len(results)} passed{Colors.RESET}")

    return 0 if failed == 0 else 1


def main():
    parser = argparse.ArgumentParser(description="Test Tool Calling Engine API")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL for the API (default: http://localhost:8000)",
    )
    args = parser.parse_args()

    return asyncio.run(run_tests(args.base_url))


if __name__ == "__main__":
    sys.exit(main())
