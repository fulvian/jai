import asyncio
import time
from typing import Any
from me4brain.domains.sports_nba.tools.nba_api import nba_api_advanced_stats

async def test_cache_stampede():
    print("Testing concurrent execution of nba_api_advanced_stats...")
    start_time = time.time()
    
    # Eseguiamo 4 richieste in parallelo (simulando i 8 tool calls dell'LLM)
    tasks = [
        nba_api_advanced_stats(team_id=1610612747), # Lakers
        nba_api_advanced_stats(team_id=1610612738), # Celtics
        nba_api_advanced_stats(team_id=1610612744), # Warriors
        nba_api_advanced_stats(team_id=1610612748)  # Heat
    ]
    
    results = await asyncio.gather(*tasks)
    
    end_time = time.time()
    duration = end_time - start_time
    
    success = 0
    for i, res in enumerate(results):
        if "error" in res:
            print(f"Task {i} failed: {res['error']}")
        else:
            success += 1
            team = res.get("advanced_stats", {}).get("team_name", "Unknown")
            print(f"Task {i} succeeded for team {team}")
            
    print(f"\nCompleted {success}/4 successfully in {duration:.2f} seconds.")
    if success == 4 and duration < 10.0:
        print("✅ CACHE WORKING: All requests finished quickly after the first one downloaded the data!")
    else:
        print("❌ CACHE NOT WORKING OR TOO SLOW")

if __name__ == "__main__":
    asyncio.run(test_cache_stampede())
