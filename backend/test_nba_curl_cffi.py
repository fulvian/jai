import asyncio
from curl_cffi.requests import AsyncSession


async def main():
    print("Testing with curl_cffi (Chrome TLS fingerprint spoofing)...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://stats.nba.com/",
    }
    url = "https://stats.nba.com/stats/teamestimatedmetrics?LeagueID=00&Season=2025-26&SeasonType=Regular+Season"

    try:
        async with AsyncSession(impersonate="chrome110") as s:
            resp = await s.get(url, headers=headers)
            print(f"Status: {resp.status_code}")
            print(f"Body length: {len(resp.text)}")
            if resp.status_code == 200:
                print("SUCCESS! Bypass worked.")
            else:
                print(f"FAILED. Status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"Exception: {type(e).__name__} - {str(e)}")


if __name__ == "__main__":
    asyncio.run(main())
