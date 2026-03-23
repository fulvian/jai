"""Monitoring API Routes - Endpoint per metriche, health e alerts."""

from __future__ import annotations

from typing import Any

import psutil
from fastapi import APIRouter, Response

from me4brain.core.monitoring.alerts import get_alert_manager
from me4brain.core.monitoring.health import get_health_checker
from me4brain.core.monitoring.metrics import get_metrics
from me4brain.core.monitoring.types import (
    AlertsResponse,
    HealthReport,
    StatsResponse,
)

router = APIRouter(tags=["monitoring"])


# --- Prometheus Metrics ---


@router.get("/metrics")
async def prometheus_metrics() -> Response:
    """
    Prometheus scrape endpoint.

    Returns:
        Metriche in formato Prometheus
    """
    metrics = get_metrics()
    output = metrics.generate_metrics()
    return Response(content=output, media_type="text/plain; charset=utf-8")


# --- Health Checks ---


@router.get("/health")
async def health_check() -> dict:
    """
    Liveness probe.

    Returns:
        Status e uptime
    """
    metrics = get_metrics()
    return {
        "status": "ok",
        "uptime_seconds": round(metrics.get_uptime(), 2),
    }


@router.get("/health/ready")
async def readiness_check() -> dict:
    """
    Readiness probe.

    Verifica che componenti essenziali siano up.

    Returns:
        Ready status
    """
    checker = get_health_checker()
    is_ready = await checker.is_ready()

    return {
        "ready": is_ready,
        "status": "ready" if is_ready else "not_ready",
    }


@router.get("/health/components", response_model=HealthReport)
async def component_health() -> HealthReport:
    """
    Health dettagliato componenti.

    Returns:
        Report con stato ogni componente
    """
    checker = get_health_checker()
    return await checker.check_all()


# --- Internal Stats ---


@router.get("/v1/monitoring/stats", response_model=StatsResponse)
async def internal_stats() -> StatsResponse:
    """
    Statistiche interne JSON.

    Returns:
        Stats sistema
    """
    metrics = get_metrics()

    # Memory usage
    process = psutil.Process()
    memory_mb = process.memory_info().rss / 1024 / 1024

    # Raccogli stats (approssimative, da metrics reali)
    return StatsResponse(
        uptime_seconds=metrics.get_uptime(),
        requests_total=0,  # Da Prometheus
        requests_per_minute=0.0,
        llm_tokens_total=0,
        llm_cost_total=0.0,
        active_sessions=0,
        memory_usage_mb=round(memory_mb, 2),
    )


# --- Alerts ---


@router.get("/v1/monitoring/alerts", response_model=AlertsResponse)
async def get_alerts() -> AlertsResponse:
    """
    Alerts attivi e risolti recenti.

    Returns:
        Lista alerts
    """
    manager = get_alert_manager()

    return AlertsResponse(
        total=len(manager.get_active_alerts()),
        firing=manager.get_active_alerts(),
        resolved_recent=manager.get_resolved_alerts(),
    )


@router.post("/v1/monitoring/alerts/clear")
async def clear_resolved_alerts() -> dict:
    """Pulisce alerts risolti."""
    manager = get_alert_manager()
    count = manager.clear_resolved()
    return {"cleared": count}


# --- SOTA 2026: Hardware Resource Monitoring ---


@router.get("/v1/monitoring/resources")
async def get_hardware_resources() -> dict[str, Any]:
    """Statistiche risorse hardware in tempo reale.

    Returns:
        RAM, GPU, CPU, Swap, LLM process memory
    """
    from me4brain.core.monitoring.resource_monitor import get_resource_monitor

    monitor = get_resource_monitor()
    stats = await monitor.get_system_stats()

    return {
        "hardware": {
            "ram": {
                "total_gb": round(stats.ram_total_gb, 2),
                "used_gb": round(stats.ram_used_gb, 2),
                "available_gb": round(stats.ram_available_gb, 2),
                "usage_pct": round(stats.ram_usage_pct, 1),
            },
            "swap": {
                "used_gb": round(stats.swap_used_gb, 2),
            },
            "cpu": {
                "usage_pct": round(stats.cpu_pct, 1),
                "load_avg": {
                    "1m": round(stats.load_avg[0], 2),
                    "5m": round(stats.load_avg[1], 2),
                    "15m": round(stats.load_avg[2], 2),
                },
            },
            "gpu": stats.gpu_metal_usage,
            "llm_processes": {
                "mlx_gb": round(stats.mlx_process_rss_gb, 2),
                "embedding_gb": round(stats.embedding_process_rss_gb, 2),
            },
        },
        "status": {
            "level": stats.resource_level.value,
            "is_under_pressure": stats.is_under_pressure,
        },
        "recommendations": monitor.get_resource_recommendations(stats),
    }


@router.get("/v1/monitoring/resources/llm-processes")
async def get_llm_processes() -> dict[str, Any]:
    """Lista processi LLM attivi con dettagli."""
    from me4brain.core.monitoring.resource_monitor import get_resource_monitor

    monitor = get_resource_monitor()
    processes = monitor.get_llm_processes()

    return {
        "processes": [
            {
                "pid": p.pid,
                "name": p.name,
                "rss_gb": round(p.rss_gb, 2),
                "cpu_pct": round(p.cpu_pct, 1),
                "cmdline": p.cmdline,
            }
            for p in processes
        ],
        "total_count": len(processes),
        "total_memory_gb": round(sum(p.rss_gb for p in processes), 2),
    }


@router.get("/v1/monitoring/context-tracker")
async def get_context_tracker_status() -> dict[str, Any]:
    """Stato del context window tracker."""
    from me4brain.engine.context_compressor import get_context_tracker

    tracker = get_context_tracker()
    return tracker.get_status()


@router.get("/v1/monitoring/compressor-stats")
async def get_compressor_stats() -> dict[str, Any]:
    """Statistiche del context compressor."""

    return {
        "note": "Per-session stats. Create a new instance for each query session.",
        "usage": "Create AdaptiveContextCompressor instance in IterativeExecutor",
    }


@router.get("/v1/monitoring/summary")
async def get_monitoring_summary() -> dict[str, Any]:
    """Riepilogo completo del monitoring."""
    from me4brain.core.monitoring.resource_monitor import get_resource_monitor
    from me4brain.engine.context_compressor import get_context_tracker

    monitor = get_resource_monitor()
    stats = await monitor.get_system_stats()
    tracker = get_context_tracker()

    return {
        "hardware": {
            "ram_usage_pct": round(stats.ram_usage_pct, 1),
            "swap_gb": round(stats.swap_used_gb, 2),
            "level": stats.resource_level.value,
            "under_pressure": stats.is_under_pressure,
        },
        "context": tracker.get_status(),
        "recommendations": monitor.get_resource_recommendations(stats)[:3],
    }
