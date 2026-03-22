"""LightRAG Implementation.

Coordina il recupero dual-level (Local & Global) integrando:
- Episodic Memory (Qdrant) -> Local/Vector
- Semantic Memory (Neo4j) -> Global/Graph
- NanoGPT -> Entity Extraction
"""

import json
from typing import Any

import structlog
from pydantic import BaseModel

from me4brain.embeddings.bge_m3 import get_embedding_service
from me4brain.llm import LLMRequest, Message, get_llm_client, get_llm_config
from me4brain.memory.episodic import Episode, get_episodic_memory
from me4brain.memory.semantic import Entity, Relation, get_semantic_memory
from me4brain.retrieval.prompts import ENTITY_EXTRACTION_PROMPT

logger = structlog.get_logger(__name__)


class LightRAGResult(BaseModel):
    """Risultato unificato di LightRAG."""

    content: str
    source: str  # 'local', 'global', 'hybrid'
    score: float
    metadata: dict[str, Any] = {}


class LightRAG:
    """Motore LightRAG per Me4BrAIn."""

    def __init__(self, episodic=None, semantic=None):
        self.episodic = episodic or get_episodic_memory()
        self.semantic = semantic or get_semantic_memory()
        self.embedding = get_embedding_service()
        self.llm = get_llm_client()
        self.config = get_llm_config()

    async def ingest(self, text: str, tenant_id: str, user_id: str, source: str = "document"):
        """Ingegnosità incrementale: estrae entità e le salva in entrambi i layer."""
        logger.info("Starting LightRAG ingestion", tenant_id=tenant_id, text_len=len(text))

        # Assicuriamoci che gli schemi esistano
        await self.semantic.initialize()
        await self.episodic.initialize()

        # 1. Estrazione Entità e Relazioni via LLM
        extraction = await self._extract_entities_and_relations(text)

        # 2. Salvataggio su Semantic Memory (Grafo)
        for ent_data in extraction.get("entities", []):
            entity = Entity(
                id=ent_data["id"],
                type=ent_data["type"],
                name=ent_data["name"],
                tenant_id=tenant_id,
                properties={"description": ent_data.get("description", "")},
            )
            await self.semantic.add_entity(entity)

        for rel_data in extraction.get("relations", []):
            relation = Relation(
                source_id=rel_data["source"],
                target_id=rel_data["target"],
                type=rel_data["type"],
                tenant_id=tenant_id,
                weight=rel_data.get("weight", 1.0),
                properties={"description": rel_data.get("description", "")},
            )
            await self.semantic.add_relation(relation)

        # 3. Salvataggio su Episodic Memory (Vettoriale)
        # Creiamo un "episodio" per ogni entità estratta per facilitare il Local Retrieval
        for ent_data in extraction.get("entities", []):
            # Usiamo la descrizione come contenuto per l'embedding
            content = f"{ent_data['name']} ({ent_data['type']}): {ent_data.get('description', '')}"
            vector = self.embedding.embed_query(content)

            episode = Episode(
                tenant_id=tenant_id,
                user_id=user_id,
                content=content,
                summary=ent_data["name"],
                source=f"lightrag_extraction_{source}",
                tags=[ent_data["type"], "lightrag"],
            )
            await self.episodic.add_episode(episode, embedding=vector)

        logger.info(
            "LightRAG ingestion completed",
            entities=len(extraction.get("entities", [])),
            relations=len(extraction.get("relations", [])),
        )

    async def _extract_entities_and_relations(self, text: str) -> dict[str, Any]:
        """Chiamata a NanoGPT per estrazione strutturata."""
        prompt = ENTITY_EXTRACTION_PROMPT.format(text=text)
        # qwen3.5 thinking models produce extensive thinking traces (8000+ tokens)
        # plus actual content (~500-1000 tokens). We need high max_tokens to allow
        # both thinking AND actual JSON content to be generated.
        request = LLMRequest(
            model=self.config.model_extraction,
            messages=[Message(role="user", content=prompt)],
            temperature=0.1,
            max_tokens=8000,  # Must be high enough for thinking + content
        )

        response = await self.llm.generate_response(request)
        content = response.choices[0].message.content or ""

        # Pulizia dell'output se il modello è verboso o include markdown
        json_str = self._clean_json_content(content)

        try:
            result = json.loads(json_str)
            # Validate structure
            if not isinstance(result, dict):
                logger.warning("extraction_invalid_structure", type=type(result).__name__)
                return {"entities": [], "relations": []}
            return result
        except json.JSONDecodeError:
            logger.error(
                "Failed to decode LLM extraction JSON",
                content=content[:500] if content else "EMPTY",
            )
            return {"entities": [], "relations": []}

    def _clean_json_content(self, content: str) -> str:
        """Estrae il blocco JSON principale dal contenuto della risposta LLM."""
        if not content:
            return "{}"

        # 1. Rimuovi blocchi markdown ```json ... ```
        import re

        json_match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
        if json_match:
            return json_match.group(1)

        # 2. Rimuovi blocchi markdown generici ``` ... ```
        json_match = re.search(r"```\s*(\{.*?\})\s*```", content, re.DOTALL)
        if json_match:
            return json_match.group(1)

        # 3. Cerca la prima { e l'ultima }
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1:
            return content[start : end + 1]

        return content.strip()

    async def dual_retrieval(
        self, query: str, tenant_id: str, top_k: int = 10
    ) -> list[LightRAGResult]:
        """Esegue il recupero combinato Local + Global con RRF Fusion."""
        logger.debug("Executing Dual-Level Retrieval", query=query)

        # 1. Recupero Local (Qdrant)
        query_vector = self.embedding.embed_query(query)
        local_episodes = await self.episodic.search_similar(
            tenant_id=tenant_id,
            user_id=None,
            query_embedding=query_vector,
            limit=top_k * 2,
        )

        # 2. Recupero Global (Neo4j PPR)
        # Usiamo i nomi delle entità trovate nel local search come seed per il PPR
        seed_entities = [ep.summary for ep, _ in local_episodes if ep.summary]

        ppr_results = await self.semantic.personalized_pagerank(
            tenant_id=tenant_id, seed_entities=seed_entities[:5], top_k=top_k * 2
        )

        # Trasformiamo PPR results (ID, score) in oggetti Entity
        graph_results = []
        for eid, score in ppr_results:
            entity = await self.semantic.get_entity(tenant_id, eid)
            if entity:
                graph_results.append({"entity": entity, "score": score})

        # 3. RRF Fusion (Reciprocal Rank Fusion)
        return self._rrf_fusion(local_episodes, graph_results, top_k)

    def _rrf_fusion(
        self, local_results: list, graph_results: list, top_k: int, k: int = 60
    ) -> list[LightRAGResult]:
        """Algoritmo Reciprocal Rank Fusion."""
        scores = {}  # key: content/id, value: score
        metadata_map = {}

        # Process Local (Vector)
        for i, (res, score) in enumerate(local_results):
            # Identificatore univoco per il contenuto
            key = res.content
            scores[key] = scores.get(key, 0) + 1.0 / (k + i + 1)
            metadata_map[key] = {"source": "local", "orig_score": score}

        # Process Global (Graph)
        for i, res in enumerate(graph_results):
            # res in semantic.py è un dict con 'entity' e 'score'
            entity = res["entity"]
            key = f"{entity.name}: {entity.properties.get('description', '')}"
            scores[key] = scores.get(key, 0) + 1.0 / (k + i + 1)
            metadata_map[key] = {"source": "global", "orig_score": res["score"]}

        # Sort by unified score
        sorted_keys = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        final_results = []
        for key in sorted_keys[:top_k]:
            final_results.append(
                LightRAGResult(
                    content=key,
                    source=metadata_map[key]["source"],
                    score=scores[key],
                    metadata=metadata_map[key],
                )
            )

        return final_results
