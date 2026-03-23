"""Me4BrAIn Memory Module.

Quattro layer cognitivi del sistema di memoria:
- Working Memory (Layer I): STM con Redis + NetworkX
- Episodic Memory (Layer II): LTM con Qdrant
- Semantic Memory (Layer III): Knowledge Graph con Neo4j
- Procedural Memory (Layer IV): Skill & Muscle Memory
"""

from me4brain.memory.entity_extractor import (
    EntityExtractionResult,
    EntityExtractor,
    ExtractedEntity,
    extract_and_store_entities,
    get_entity_extractor,
)
from me4brain.memory.episodic import (
    Episode,
    EpisodicMemory,
    get_episodic_memory,
)
from me4brain.memory.lexical_search import (
    BM25Indexer,
    LexicalSearchService,
    get_lexical_search_service,
)
from me4brain.memory.procedural import (
    ProceduralMemory,
    Tool,
    ToolExecution,
    get_procedural_memory,
)
from me4brain.memory.semantic import (
    Entity,
    Relation,
    SemanticMemory,
    get_semantic_memory,
)
from me4brain.memory.working import (
    WorkingMemory,
    get_working_memory,
)

__all__ = [
    # Working Memory
    "WorkingMemory",
    "get_working_memory",
    # Episodic Memory
    "Episode",
    "EpisodicMemory",
    "get_episodic_memory",
    # Semantic Memory
    "Entity",
    "Relation",
    "SemanticMemory",
    "get_semantic_memory",
    # Procedural Memory
    "Tool",
    "ToolExecution",
    "ProceduralMemory",
    "get_procedural_memory",
    # Lexical Search
    "BM25Indexer",
    "LexicalSearchService",
    "get_lexical_search_service",
    # Entity Extraction (OPT-014)
    "EntityExtractor",
    "ExtractedEntity",
    "EntityExtractionResult",
    "get_entity_extractor",
    "extract_and_store_entities",
]
