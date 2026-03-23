import asyncio
import httpx


async def main():
    print("Testing with HTTP/2 enabled...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://stats.nba.com/",
    }
    try:
        async with httpx.AsyncClient(http2=True, timeout=10.0) as client:
            resp = await client.get(
                "https://stats.nba.com/stats/teamestimatedmetrics?LeagueID=00&Season=2025-26&SeasonType=Regular+Season",
                headers=headers,
            )
            print(f"Status: {resp.status_code}")
            print(f"Body length: {len(resp.text)}")
    except Exception as e:
        print(f"Failed: {type(e).__name__} - {str(e)}")


if __name__ == "__main__":
    asyncio.run(main())
