"""Hardware Resource Monitor - SOTA 2026.

Monitora risorse hardware per LLM locale su Apple Silicon:
- RAM unificata
- GPU Metal usage
- MLX process memory
- Swap usage
- CPU load

Fornisce alerting per memory pressure e OOM prevention.
"""

from __future__ import annotations

import asyncio
import platform
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import psutil
import structlog

logger = structlog.get_logger(__name__)


class ResourceLevel(str, Enum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class SystemStats:
    """Statistiche sistema in tempo reale."""

    ram_total_gb: float
    ram_used_gb: float
    ram_available_gb: float
    ram_usage_pct: float
    gpu_metal_usage: Optional[dict[str, Any]] = None
    mlx_process_rss_gb: float = 0.0
    embedding_process_rss_gb: float = 0.0
    swap_used_gb: float = 0.0
    cpu_pct: float = 0.0
    load_avg: tuple[float, float, float] = (0.0, 0.0, 0.0)
    timestamp: float = field(default_factory=time.time)

    @property
    def resource_level(self) -> ResourceLevel:
        if self.ram_usage_pct > 90 or self.swap_used_gb > 4.0:
            return ResourceLevel.CRITICAL
        elif self.ram_usage_pct > 75 or self.swap_used_gb > 2.0:
            return ResourceLevel.WARNING
        return ResourceLevel.NORMAL

    @property
    def is_under_pressure(self) -> bool:
        return self.resource_level != ResourceLevel.NORMAL


@dataclass
class LLMProcessInfo:
    """Info su processo LLM locale."""

    pid: int
    name: str
    rss_gb: float
    cpu_pct: float
    cmdline: list[str]


class HardwareResourceMonitor:
    """Monitora risorse hardware per LLM locale su Apple Silicon.

    Soglie di allarme configurabili:
    - MEMORY_WARNING_PCT: 75% RAM usata
    - MEMORY_CRITICAL_PCT: 90% RAM usata → degradazione LLM
    - SWAP_WARNING_GB: 2GB swap → warning
    - SWAP_CRITICAL_GB: 4GB swap → degradazione severa
    """

    MEMORY_WARNING_PCT = 75.0
    MEMORY_CRITICAL_PCT = 90.0
    SWAP_WARNING_GB = 2.0
    SWAP_CRITICAL_GB = 4.0
    POLL_INTERVAL_SECONDS = 5.0

    def __init__(self):
        self._last_stats: Optional[SystemStats] = None
        self._stats_history: list[SystemStats] = []
        self._max_history = 100
        self._monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None

    async def get_system_stats(self) -> SystemStats:
        """Statistiche sistema in tempo reale."""
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        load_avg = (0.0, 0.0, 0.0)
        try:
            load_avg = tuple(psutil.getloadavg())
        except (AttributeError, OSError):
            pass

        cpu_pct = psutil.cpu_percent(interval=0.1)

        gpu_usage = await self._get_metal_usage()
        mlx_memory = self._get_process_memory("mlx_lm")
        embedding_memory = self._get_process_memory("python")

        stats = SystemStats(
            ram_total_gb=mem.total / (1024**3),
            ram_used_gb=mem.used / (1024**3),
            ram_available_gb=mem.available / (1024**3),
            ram_usage_pct=mem.percent,
            gpu_metal_usage=gpu_usage,
            mlx_process_rss_gb=mlx_memory,
            embedding_process_rss_gb=embedding_memory,
            swap_used_gb=swap.used / (1024**3),
            cpu_pct=cpu_pct,
            load_avg=load_avg,
        )

        self._last_stats = stats
        self._stats_history.append(stats)
        if len(self._stats_history) > self._max_history:
            self._stats_history.pop(0)

        return stats

    async def _get_metal_usage(self) -> Optional[dict[str, Any]]:
        """Rileva utilizzo GPU Metal (Apple Silicon)."""
        if platform.system() != "Darwin":
            return None

        try:
            result = subprocess.run(
                ["ioreg", "-r", "-d", "1", "-c", "IOAccelerator"],
                capture_output=True,
                text=True,
                timeout=2,
            )

            if result.returncode != 0:
                return None

            output = result.stdout

            vram_match = None
            for line in output.split("\n"):
                if "VRAM" in line or "MemSize" in line:
                    vram_match = line.strip()

            return {
                "raw_output_preview": output[:500] if output else None,
                "vram_hint": vram_match,
                "platform": "apple_silicon",
            }

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.debug("metal_usage_check_failed", error=str(e))
            return None

    def _get_process_memory(self, process_hint: str) -> float:
        """Memoria usata da processi che contengono un hint nel nome/cmdline."""
        total_memory = 0.0

        try:
            for proc in psutil.process_iter(["pid", "name", "memory_info", "cmdline"]):
                try:
                    name = proc.info.get("name", "") or ""
                    cmdline = proc.info.get("cmdline") or []

                    cmdline_str = " ".join(str(c) for c in cmdline).lower()

                    if process_hint.lower() in name.lower() or process_hint.lower() in cmdline_str:
                        mem_info = proc.info.get("memory_info")
                        if mem_info:
                            total_memory += mem_info.rss / (1024**3)

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        except Exception as e:
            logger.warning("process_memory_check_failed", error=str(e))

        return total_memory

    def get_llm_processes(self) -> list[LLMProcessInfo]:
        """Lista processi LLM attivi con dettagli."""
        processes = []

        llm_hints = ["mlx_lm", "ollama", "lmstudio", "python"]

        try:
            for proc in psutil.process_iter(
                ["pid", "name", "memory_info", "cpu_percent", "cmdline"]
            ):
                try:
                    name = proc.info.get("name", "") or ""
                    cmdline = proc.info.get("cmdline") or []
                    cmdline_str = " ".join(str(c) for c in cmdline).lower()

                    is_llm = any(hint in name.lower() or hint in cmdline_str for hint in llm_hints)

                    if is_llm:
                        mem_info = proc.info.get("memory_info")
                        cpu_pct = proc.info.get("cpu_percent", 0) or 0

                        processes.append(
                            LLMProcessInfo(
                                pid=proc.info["pid"],
                                name=name,
                                rss_gb=mem_info.rss / (1024**3) if mem_info else 0,
                                cpu_pct=cpu_pct,
                                cmdline=cmdline[:5] if cmdline else [],
                            )
                        )

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        except Exception as e:
            logger.warning("llm_process_list_failed", error=str(e))

        return processes

    def should_use_cloud_fallback(self, stats: Optional[SystemStats] = None) -> bool:
        """Determina se il sistema è sotto pressione e serve il cloud."""
        if stats is None:
            stats = self._last_stats

        if stats is None:
            return False

        return (
            stats.ram_usage_pct > self.MEMORY_CRITICAL_PCT
            or stats.swap_used_gb > self.SWAP_CRITICAL_GB
        )

    def get_resource_recommendations(self, stats: Optional[SystemStats] = None) -> list[str]:
        """Genera raccomandazioni basate sullo stato delle risorse."""
        if stats is None:
            stats = self._last_stats

        if stats is None:
            return ["Impossibile ottenere statistiche sistema"]

        recommendations = []

        if stats.ram_usage_pct > self.MEMORY_CRITICAL_PCT:
            recommendations.append(
                f"CRITICO: RAM al {stats.ram_usage_pct:.1f}%. "
                "Chiudere applicazioni o usare cloud fallback."
            )
        elif stats.ram_usage_pct > self.MEMORY_WARNING_PCT:
            recommendations.append(
                f"ATTENZIONE: RAM al {stats.ram_usage_pct:.1f}%. Monitorare l'uso memoria."
            )

        if stats.swap_used_gb > self.SWAP_CRITICAL_GB:
            recommendations.append(
                f"CRITICO: Swap {stats.swap_used_gb:.1f}GB. "
                "Prestazioni LLM degradate. Considerare cloud."
            )
        elif stats.swap_used_gb > self.SWAP_WARNING_GB:
            recommendations.append(
                f"ATTENZIONE: Swap {stats.swap_used_gb:.1f}GB. Possibile degradazione prestazioni."
            )

        if stats.mlx_process_rss_gb > 8.0:
            recommendations.append(
                f"Processo MLX usa {stats.mlx_process_rss_gb:.1f}GB. "
                "Considerare modello più piccolo."
            )

        if not recommendations:
            recommendations.append("Risorse sistema ottimali per LLM locale.")

        return recommendations

    async def start_monitoring(self, interval: float = 5.0) -> None:
        """Avvia monitoring continuo in background."""
        if self._monitoring:
            return

        self._monitoring = True
        self.POLL_INTERVAL_SECONDS = interval

        async def monitor_loop():
            while self._monitoring:
                try:
                    stats = await self.get_system_stats()

                    if stats.resource_level == ResourceLevel.CRITICAL:
                        logger.warning(
                            "resource_critical",
                            ram_pct=stats.ram_usage_pct,
                            swap_gb=stats.swap_used_gb,
                        )
                    elif stats.resource_level == ResourceLevel.WARNING:
                        logger.info(
                            "resource_warning",
                            ram_pct=stats.ram_usage_pct,
                            swap_gb=stats.swap_used_gb,
                        )

                    await asyncio.sleep(self.POLL_INTERVAL_SECONDS)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("monitoring_error", error=str(e))
                    await asyncio.sleep(self.POLL_INTERVAL_SECONDS)

        self._monitor_task = asyncio.create_task(monitor_loop())
        logger.info("resource_monitoring_started", interval=interval)

    async def stop_monitoring(self) -> None:
        """Ferma monitoring continuo."""
        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        logger.info("resource_monitoring_stopped")

    def get_stats_summary(self) -> dict[str, Any]:
        """Riepilogo statistiche dalla history."""
        if not self._stats_history:
            return {"error": "Nessuna statistica disponibile"}

        recent = self._stats_history[-10:]

        avg_ram = sum(s.ram_usage_pct for s in recent) / len(recent)
        max_ram = max(s.ram_usage_pct for s in recent)
        avg_swap = sum(s.swap_used_gb for s in recent) / len(recent)
        max_swap = max(s.swap_used_gb for s in recent)

        return {
            "samples": len(self._stats_history),
            "avg_ram_usage_pct": round(avg_ram, 1),
            "max_ram_usage_pct": round(max_ram, 1),
            "avg_swap_gb": round(avg_swap, 2),
            "max_swap_gb": round(max_swap, 2),
            "current_level": self._last_stats.resource_level.value
            if self._last_stats
            else "unknown",
        }


_resource_monitor: Optional[HardwareResourceMonitor] = None


def get_resource_monitor() -> HardwareResourceMonitor:
    """Ottiene il singleton del resource monitor."""
    global _resource_monitor
    if _resource_monitor is None:
        _resource_monitor = HardwareResourceMonitor()
    return _resource_monitor
