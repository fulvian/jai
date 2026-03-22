import asyncio
from me4brain.domains.geo_weather.tools.geo_api import openmeteo_weather


async def test():
    res = await openmeteo_weather("Caltanissetta, IT")
    print(res)


asyncio.run(test())
