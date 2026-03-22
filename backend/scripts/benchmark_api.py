#!/usr/bin/env python
"""Benchmark Script for Me4BrAIn API.

Measures latency and throughput for critical endpoints:
- /health (baseline)
- /v1/memory/query (cognitive query)
- /v1/tools/execute (tool execution)
- /v1/memory/query/stream (streaming)

Usage:
    uv run python scripts/benchmark_api.py [--base-url http://localhost:8086] [--iterations 10]
"""

import argparse
import asyncio
import statistics
import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class BenchmarkResult:
    """Result of a benchmark run."""

    endpoint: str
    method: str
    iterations: int
    latencies_ms: list[float]
    errors: int

    @property
    def avg_ms(self) -> float:
        return statistics.mean(self.latencies_ms) if self.latencies_ms else 0

    @property
    def p50_ms(self) -> float:
        return statistics.median(self.latencies_ms) if self.latencies_ms else 0

    @property
    def p95_ms(self) -> float:
        if not self.latencies_ms:
            return 0
        sorted_lat = sorted(self.latencies_ms)
        idx = int(len(sorted_lat) * 0.95)
        return sorted_lat[idx]

    @property
    def p99_ms(self) -> float:
        if not self.latencies_ms:
            return 0
        sorted_lat = sorted(self.latencies_ms)
        idx = int(len(sorted_lat) * 0.99)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]

    @property
    def throughput_rps(self) -> float:
        total_time_s = sum(self.latencies_ms) / 1000
        return len(self.latencies_ms) / total_time_s if total_time_s > 0 else 0


async def benchmark_endpoint(
    client: httpx.AsyncClient,
    method: str,
    endpoint: str,
    iterations: int,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> BenchmarkResult:
    """Run benchmark for a single endpoint."""
    latencies: list[float] = []
    errors = 0

    default_headers = {
        "X-Tenant-ID": "benchmark_tenant",
        "X-User-ID": "benchmark_user",
    }
    if headers:
        default_headers.update(headers)

    for _ in range(iterations):
        start = time.perf_counter()
        try:
            if method == "GET":
                resp = await client.get(endpoint, headers=default_headers)
            else:
                resp = await client.post(endpoint, json=json_body, headers=default_headers)

            if resp.status_code >= 400:
                errors += 1
            else:
                elapsed_ms = (time.perf_counter() - start) * 1000
                latencies.append(elapsed_ms)
        except Exception:
            errors += 1

    return BenchmarkResult(
        endpoint=endpoint,
        method=method,
        iterations=iterations,
        latencies_ms=latencies,
        errors=errors,
    )


async def run_benchmarks(base_url: str, iterations: int) -> list[BenchmarkResult]:
    """Run all benchmarks."""
    results: list[BenchmarkResult] = []

    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        # 1. Health check (baseline)
        print("📊 Benchmarking /health...")
        result = await benchmark_endpoint(client, "GET", "/health", iterations)
        results.append(result)

        # 2. Cognitive query (non-streaming)
        print("📊 Benchmarking /v1/memory/query...")
        result = await benchmark_endpoint(
            client,
            "POST",
            "/v1/memory/query",
            min(iterations, 3),  # Reduce iterations (slow endpoint)
            json_body={"query": "Qual è il tempo attuale?"},
        )
        results.append(result)

        # 3. Tool catalog - GET requires proper path
        print("📊 Benchmarking /v1/procedural/tools...")
        result = await benchmark_endpoint(
            client,
            "GET",
            "/v1/procedural/tools?limit=10",
            iterations,
        )
        results.append(result)

        # 4. Working memory context
        print("📊 Benchmarking /v1/working/context...")
        result = await benchmark_endpoint(
            client,
            "GET",
            "/v1/working/context",
            iterations,
        )
        results.append(result)

    return results


def print_results(results: list[BenchmarkResult]) -> None:
    """Print benchmark results in a table."""
    print("\n" + "=" * 80)
    print("BENCHMARK RESULTS")
    print("=" * 80)
    print(f"{'Endpoint':<40} {'Avg':>8} {'P50':>8} {'P95':>8} {'P99':>8} {'RPS':>8} {'Err':>5}")
    print("-" * 80)

    for r in results:
        print(
            f"{r.endpoint:<40} "
            f"{r.avg_ms:>7.1f}ms "
            f"{r.p50_ms:>7.1f}ms "
            f"{r.p95_ms:>7.1f}ms "
            f"{r.p99_ms:>7.1f}ms "
            f"{r.throughput_rps:>7.1f} "
            f"{r.errors:>5}"
        )

    print("=" * 80)
    print("\nLegend: Avg/P50/P95/P99 = Latency (ms), RPS = Requests/sec, Err = Errors")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Me4BrAIn API")
    parser.add_argument("--base-url", default="http://localhost:8086", help="API base URL")
    parser.add_argument("--iterations", type=int, default=10, help="Iterations per endpoint")
    args = parser.parse_args()

    print(f"🚀 Starting benchmark against {args.base_url}")
    print(f"   Iterations per endpoint: {args.iterations}")
    print()

    results = asyncio.run(run_benchmarks(args.base_url, args.iterations))
    print_results(results)


if __name__ == "__main__":
    main()
