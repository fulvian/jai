import asyncio
from neo4j import AsyncGraphDatabase


async def check():
    uri = "bolt://100.99.43.29:7687"
    driver = AsyncGraphDatabase.driver(uri, auth=("neo4j", "neo4j_secret"))
    async with driver.session() as session:
        res = await session.run("SHOW VECTOR INDEXES YIELD *")
        async for r in res:
            d = dict(r)
            if d.get("name") == "fewshot_embeddings":
                options = d.get("options", {})
                config = options.get("indexConfig", {})
                print(f"Index fewshot_embeddings dimensions: {config.get('vector.dimensions')}")
    await driver.close()


asyncio.run(check())
