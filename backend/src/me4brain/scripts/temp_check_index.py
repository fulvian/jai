
import asyncio
import os
import sys
from qdrant_client import QdrantClient, AsyncQdrantClient

# Aggiungi src al path
sys.path.append(os.path.join(os.getcwd(), "src"))

from me4brain.engine.hybrid_router.tool_index import ToolIndexManager
from llama_index.core.retrievers import VectorIndexRetriever
from me4brain.engine.hybrid_router.llama_tool_retriever import LlamaIndexToolRetriever
from me4brain.engine.hybrid_router.types import DomainClassification, DomainComplexity

async def test_retrieval():
    host = "localhost"
    port = 6333
    
    client = QdrantClient(url=f"http://{host}:{port}")
    aclient = AsyncQdrantClient(url=f"http://{host}:{port}")
    
    # 1. Initialize manager and retriever
    manager = ToolIndexManager(client, aclient)
    await manager.initialize()
    
    retriever = LlamaIndexToolRetriever(manager)
    await retriever.initialize()

    query = "che tempo fa a Caltanissetta?"

    # 2. Test retrieval with geo_weather domain
    print(f"\nSearching for '{query}' in 'geo_weather' domain...")
    classification = DomainClassification(
        domains=[DomainComplexity(name="geo_weather", complexity="low")],
        confidence=0.98,
        query_summary="Weather test"
    )
    
    result = await retriever.retrieve(query, classification)
    print(f"Retrieved {len(result.tools)} tools.")
    for t in result.tools:
        print(f"- Tool: {t.name}, Score: {t.similarity_score:.4f}, Domain: {t.domain}")

    # 3. Test global retrieval (no domain filter)
    print(f"\nGlobal searching (no domain filter) for '{query}'...")
    global_result = await retriever.retrieve_global_topk(query, k=10)
    print(f"Retrieved {len(global_result.tools)} tools globally.")
    for t in global_result.tools:
        print(f"- Tool: {t.name}, Score: {t.similarity_score:.4f}, Domain: {t.domain}")

    # 4. Check raw nodes from index to see actual scores BEFORE filtering
    print(f"\nInspecting RAW nodes from index for '{query}'...")
    index = manager.index # Changed from index_manager.index to manager.index
    vector_retriever = VectorIndexRetriever(index=index, similarity_top_k=10)
    nodes = await vector_retriever.aretrieve(query)
    print(f"Found {len(nodes)} raw nodes.")
    for i, node in enumerate(nodes):
        print(f"[{i}] Tool: {node.node.metadata.get('tool_name')}, Score: {node.score:.4f}, Domain: {node.node.metadata.get('domain')}")

if __name__ == "__main__":
    asyncio.run(test_retrieval())
