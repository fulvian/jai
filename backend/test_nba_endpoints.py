import sys
import time


def test_endpoints():
    from nba_api.stats.endpoints import teamestimatedmetrics, leaguestandings
    from me4brain.domains.sports_nba.tools.nba_api import _get_nba_stats_headers

    print("Testing teamestimatedmetrics with 30s timeout...", flush=True)
    try:
        start_time = time.time()
        metrics = teamestimatedmetrics.TeamEstimatedMetrics(
            season="2025-26", timeout=30, headers=_get_nba_stats_headers()
        )
        data = metrics.get_dict()
        duration = time.time() - start_time
        print(f"Success! Keys: {data.keys()} in {duration:.2f}s", flush=True)
    except Exception as e:
        duration = time.time() - start_time
        print(f"Failed teamestimatedmetrics: {str(e)} in {duration:.2f}s", flush=True)

    print("\nTesting leaguestandings with 30s timeout...", flush=True)
    try:
        start_time = time.time()
        standings = leaguestandings.LeagueStandings(
            season="2025-26", league_id="00", timeout=30, headers=_get_nba_stats_headers()
        )
        data = standings.get_dict()
        duration = time.time() - start_time
        print(f"Success! Keys: {data.keys()} in {duration:.2f}s", flush=True)
    except Exception as e:
        duration = time.time() - start_time
        print(f"Failed leaguestandings: {str(e)} in {duration:.2f}s", flush=True)


if __name__ == "__main__":
    test_endpoints()
