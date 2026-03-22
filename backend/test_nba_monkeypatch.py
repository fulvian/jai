import sys
from pprint import pprint

# Monkey patch requests BEFORE importing nba_api
import requests
from curl_cffi import requests as cffi_requests

class SpoofedSession(cffi_requests.Session):
    def __init__(self, *args, **kwargs):
        kwargs["impersonate"] = "chrome110"  # Force impersonation on all requests
        super().__init__(*args, **kwargs)

requests.Session = SpoofedSession
requests.get = cffi_requests.get

# Now import nba_api
from nba_api.stats.endpoints import leaguestandings

def main():
    print("Testing nba_api leaguestandings with monkey-patched requests...")
    try:
        standings = leaguestandings.LeagueStandings(
            season="2025-26", league_id="00", timeout=10
        )
        data = standings.get_dict()
        print(f"SUCCESS! Got keys: {data.keys()}")
    except Exception as e:
        print(f"FAILED: {type(e).__name__} - {str(e)}")

if __name__ == "__main__":
    main()
