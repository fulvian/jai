"""Me4BrAIn Memory Module.

Quattro layer cognitivi del sistema di memoria:
- Working Memory (Layer I): STM con Redis + NetworkX
- Episodic Memory (Layer II): LTM con Qdrant
- Semantic Memory (Layer III): Knowledge Graph con Neo4j
- Procedural Memory (Layer IV): Skill & Muscle Memory
"""

from me4brain.memory.episodic import (
    Episode,
    EpisodicMemory,
    get_episodic_memory,
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
]
