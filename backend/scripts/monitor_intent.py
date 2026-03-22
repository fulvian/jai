#!/usr/bin/env python3
"""
Monitoring script for Unified Intent Analysis system.
Tracks metrics and displays real-time dashboard.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from me4brain.engine.feature_flags import get_feature_flag_manager  # noqa: E402
from me4brain.engine.intent_cache import get_intent_cache  # noqa: E402
from me4brain.engine.intent_monitoring import get_intent_monitor  # noqa: E402
from me4brain.llm.config import get_llm_config  # noqa: E402


class IntentMonitoringDashboard:
    """Real-time monitoring dashboard for intent analysis."""

    def __init__(self):
        self.config = get_llm_config()
        self.ffm = get_feature_flag_manager()
        self.cache = get_intent_cache()
        self.monitor = get_intent_monitor()
        self.start_time = datetime.now()

    def clear_screen(self):
        """Clear terminal screen."""
        print("\033[2J\033[H", end="")

    def print_header(self):
        """Print dashboard header."""
        print("╔" + "═" * 78 + "╗")
        print("║" + " " * 20 + "UNIFIED INTENT ANALYSIS MONITORING" + " " * 25 + "║")
        print(
            "║"
            + " " * 25
            + f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            + " " * 27
            + "║"
        )
        print("╚" + "═" * 78 + "╝")
        print()

    def print_configuration(self):
        """Print current configuration."""
        print("┌─ CONFIGURATION " + "─" * 63 + "┐")
        print(f"│ Feature Flag Enabled:        {str(self.config.use_unified_intent_analyzer):50} │")
        print(f"│ Rollout Phase:               {str(self.ffm.current_phase.value):50} │")
        print(f"│ Traffic Percentage:          {str(f'{self.ffm.traffic_percentage}%'):50} │")
        print(
            f"│ Intent Analysis Timeout:     {str(f'{self.config.intent_analysis_timeout}s'):50} │"
        )
        print(f"│ Cache TTL:                   {str(f'{self.config.intent_cache_ttl}s'):50} │")
        print(f"│ Analysis Model:              {str(self.config.intent_analysis_model):50} │")
        print("└" + "─" * 78 + "┘")
        print()

    def print_cache_metrics(self):
        """Print cache metrics."""
        cache_stats = self.cache.get_stats()
        print("┌─ CACHE METRICS " + "─" * 63 + "┐")
        print(f"│ Cache Size:                  {str(f'{cache_stats.size} / 10000 entries'):50} │")
        print(f"│ Hit Rate:                    {str(f'{cache_stats.hit_rate:.1%}'):50} │")
        print(f"│ Total Hits:                  {str(cache_stats.hits):50} │")
        print(f"│ Total Misses:                {str(cache_stats.misses):50} │")
        print(f"│ Avg Latency (hit):           {str(f'{cache_stats.avg_latency_ms:.1f}ms'):50} │")
        print("└" + "─" * 78 + "┘")
        print()

    def print_intent_metrics(self):
        """Print intent analysis metrics."""
        metrics = self.monitor.get_metrics()
        print("┌─ INTENT ANALYSIS METRICS " + "─" * 52 + "┐")
        print(f"│ Total Queries:               {str(metrics.get('total_queries', 0)):50} │")
        print(f"│ Successful:                  {str(metrics.get('successful_analyses', 0)):50} │")
        print(f"│ Failed:                      {str(metrics.get('total_errors', 0)):50} │")
        error_rate = metrics.get("error_rate", 0)
        avg_lat = metrics.get("avg_latency_ms", 0)
        min_lat = metrics.get("min_latency_ms", 0)
        max_lat = metrics.get("max_latency_ms", 0)
        print(f"│ Error Rate:                  {error_rate * 100:.1f}%{'':44} │")
        print(f"│ Avg Latency:                 {avg_lat:.1f}ms{'':42} │")
        print(f"│ Min Latency:                 {min_lat:.1f}ms{'':42} │")
        print(f"│ Max Latency:                 {max_lat:.1f}ms{'':42} │")
        print("└" + "─" * 78 + "┘")
        print()

    def print_accuracy_metrics(self):
        """Print accuracy metrics by query type."""
        metrics = self.monitor.get_metrics()
        print("┌─ ACCURACY METRICS " + "─" * 59 + "┐")
        weather_acc = metrics.get("weather_accuracy", 0)
        conv_acc = metrics.get("conversational_accuracy", 0)
        multi_acc = metrics.get("multi_domain_accuracy", 0)
        overall_acc = metrics.get("overall_accuracy", 0)
        print(f"│ Weather Queries:             {weather_acc * 100:.1f}%{'':42} │")
        print(f"│ Conversational Queries:      {conv_acc * 100:.1f}%{'':41} │")
        print(f"│ Multi-Domain Queries:        {multi_acc * 100:.1f}%{'':41} │")
        print(f"│ Overall Accuracy:            {overall_acc * 100:.1f}%{'':42} │")
        print("└" + "─" * 78 + "┘")
        print()

    def print_domain_distribution(self):
        """Print domain distribution."""
        metrics = self.monitor.get_metrics()
        domains = metrics.get("domain_distribution", {})
        print("┌─ DOMAIN DISTRIBUTION " + "─" * 56 + "┐")
        if domains:
            for domain, count in sorted(domains.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"│ {domain:30} {str(count):45} │")
        else:
            print("│ No data yet" + " " * 66 + "│")
        print("└" + "─" * 78 + "┘")
        print()

    def print_alerts(self):
        """Print active alerts."""
        metrics = self.monitor.get_metrics()
        alerts = []

        # Check latency
        if metrics.get("avg_latency_ms", 0) > 200:
            alerts.append(
                f"⚠ High latency: {metrics.get('avg_latency_ms', 0):.1f}ms (target: <200ms)"
            )

        # Check error rate
        if metrics.get("error_rate", 0) > 0.01:
            alerts.append(f"⚠ High error rate: {metrics.get('error_rate', 0):.1%} (target: <1%)")

        # Check cache hit rate
        cache_stats = self.cache.get_stats()
        if cache_stats.hit_rate < 0.3:
            alerts.append(f"⚠ Low cache hit rate: {cache_stats.hit_rate:.1%} (target: >40%)")

        # Check accuracy
        if metrics.get("weather_accuracy", 0) < 0.95:
            alerts.append(
                f"⚠ Low weather accuracy: {metrics.get('weather_accuracy', 0):.1%} (target: ≥95%)"
            )

        if metrics.get("conversational_accuracy", 0) < 0.98:
            alerts.append(
                f"⚠ Low conversational accuracy: {metrics.get('conversational_accuracy', 0):.1%} (target: ≥98%)"
            )

        print("┌─ ALERTS " + "─" * 69 + "┐")
        if alerts:
            for alert in alerts:
                print(f"│ {alert:76} │")
        else:
            print("│ ✓ All systems nominal" + " " * 55 + "│")
        print("└" + "─" * 78 + "┘")
        print()

    def print_recommendations(self):
        """Print recommendations based on metrics."""
        metrics = self.monitor.get_metrics()
        cache_stats = self.cache.get_stats()
        recommendations = []

        # Latency recommendations
        if metrics.get("avg_latency_ms", 0) > 150:
            recommendations.append("→ Consider increasing cache size or enabling batch processing")

        # Cache recommendations
        if cache_stats.hit_rate < 0.3:
            recommendations.append("→ Increase cache TTL or cache size to improve hit rate")

        # Accuracy recommendations
        if metrics.get("weather_accuracy", 0) < 0.95:
            recommendations.append(
                "→ Review weather query misclassifications and update domain definitions"
            )

        if recommendations:
            print("┌─ RECOMMENDATIONS " + "─" * 60 + "┐")
            for rec in recommendations:
                print(f"│ {rec:76} │")
            print("└" + "─" * 78 + "┘")
            print()

    def print_footer(self):
        """Print dashboard footer."""
        uptime = datetime.now() - self.start_time
        print(f"Uptime: {uptime.total_seconds():.0f}s | Press Ctrl+C to exit")

    async def run(self, refresh_interval: int = 5):
        """Run the monitoring dashboard."""
        try:
            while True:
                self.clear_screen()
                self.print_header()
                self.print_configuration()
                self.print_cache_metrics()
                self.print_intent_metrics()
                self.print_accuracy_metrics()
                self.print_domain_distribution()
                self.print_alerts()
                self.print_recommendations()
                self.print_footer()

                await asyncio.sleep(refresh_interval)
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped.")
            sys.exit(0)


async def main():
    """Main entry point."""
    dashboard = IntentMonitoringDashboard()

    # Check if feature flag is enabled
    if not dashboard.config.use_unified_intent_analyzer:
        print("⚠ Warning: USE_UNIFIED_INTENT_ANALYZER is not enabled")
        print("Set USE_UNIFIED_INTENT_ANALYZER=true in .env to enable monitoring")
        sys.exit(1)

    print("Starting Unified Intent Analysis Monitoring Dashboard...")
    print("Refresh interval: 5 seconds")
    print("Press Ctrl+C to exit\n")

    await asyncio.sleep(2)
    await dashboard.run()


if __name__ == "__main__":
    asyncio.run(main())
