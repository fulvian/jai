import asyncio
import httpx
import logging
from pprint import pprint

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nba_diagnostic")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    # "nba_api" default agent
    "Mozilla/5.0 (Windows; U; Windows NT 6.1; rv:2.2) Gecko/20110201",
]


async def test_endpoint(url: str, headers: dict, proxy: str | None = None) -> None:
    logger.info(f"\n--- Testing URL: {url} ---")
    logger.info(f"Headers: {headers.get('User-Agent', 'Default')}")

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers)
            logger.info(f"Status Code: {response.status_code}")
            if response.status_code == 200:
                logger.info(f"Success! Body length: {len(response.text)}")
            else:
                logger.warning(f"Failed Body: {response.text[:200]}")
        except httpx.TimeoutException:
            logger.error(f"TIMEOUT! The request took longer than 10 seconds.")
        except Exception as e:
            logger.error(f"ERROR! {type(e).__name__}: {str(e)}")


async def main():
    endpoints = [
        "https://stats.nba.com/stats/teamestimatedmetrics?LeagueID=00&Season=2025-26&SeasonType=Regular+Season",
        "https://stats.nba.com/stats/leaguestandingsv3?LeagueID=00&Season=2025-26&SeasonType=Regular+Season",
        "https://www.nba.com",  # Test main site connectivity
    ]

    # 1. Test basic headers (no special tokens)
    basic_headers = {
        "User-Agent": USER_AGENTS[0],
        "Accept": "application/json, text/plain, */*",
    }

    # 2. Test full "Stealth" headers
    stealth_headers = {
        "Host": "stats.nba.com",
        "User-Agent": USER_AGENTS[0],
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token": "true",
        "Connection": "keep-alive",
        "Referer": "https://stats.nba.com/",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
    }

    for url in endpoints:
        await test_endpoint(url, basic_headers)
        if "stats.nba.com" in url:
            await test_endpoint(url, stealth_headers)


if __name__ == "__main__":
    asyncio.run(main())
