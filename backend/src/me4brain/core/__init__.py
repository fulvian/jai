"""Me4BrAIn Core Module.

Orchestrazione cognitiva basata su LangGraph:
- CognitiveState: stato condiviso del ciclo
- SemanticRouter: classificazione query
- ConflictResolver: risoluzione conflitti Vector vs Graph
- Orchestrator: grafo LangGraph per il ciclo cognitivo

Modular Architecture (Brain as a Service):
- DomainHandler: interfaccia per domain handlers
- PluginRegistry: auto-discovery e routing domains
- DomainRouter: circuit breaker e timeout protection
- ModularOrchestrator: integrazione con pipeline esistente
"""

from me4brain.core.checkpointer import (
    close_checkpointer,
    create_checkpointer,
    get_checkpointer,
)
from me4brain.core.conflict import (
    ConflictResolution,
    ConflictResolver,
    ConflictSource,
    get_conflict_resolver,
)
from me4brain.core.domain_router import (
    CircuitState,
    DomainRouter,
    DomainRouterConfig,
)
from me4brain.core.interfaces import (
    DomainCapability,
    DomainExecutionResult,
    DomainHandler,
    DomainVolatility,
    ToolRegistration,
)
from me4brain.core.modular_orchestrator import (
    ModularOrchestrator,
    get_modular_stats,
    try_modular_execution,
)
from me4brain.core.orchestrator import (
    build_cognitive_graph,
    get_cognitive_graph,
    run_cognitive_cycle,
)
from me4brain.core.plugin_registry import PluginRegistry
from me4brain.core.router import (
    QueryType,
    RouterResult,
    RoutingDecision,
    SemanticRouter,
    get_semantic_router,
)
from me4brain.core.state import (
    CognitiveState,
    Message,
    RetrievalResult,
    ToolCall,
    ToolResult,
    create_initial_state,
)

__all__ = [
    # State
    "CognitiveState",
    "Message",
    "RetrievalResult",
    "ToolCall",
    "ToolResult",
    "create_initial_state",
    # Router
    "QueryType",
    "RoutingDecision",
    "RouterResult",
    "SemanticRouter",
    "get_semantic_router",
    # Conflict
    "ConflictResolver",
    "ConflictResolution",
    "ConflictSource",
    "get_conflict_resolver",
    # Orchestrator
    "build_cognitive_graph",
    "get_cognitive_graph",
    "run_cognitive_cycle",
    # Checkpointer
    "create_checkpointer",
    "get_checkpointer",
    "close_checkpointer",
    # === NEW: Modular Architecture ===
    # Interfaces
    "DomainHandler",
    "DomainCapability",
    "DomainVolatility",
    "DomainExecutionResult",
    "ToolRegistration",
    # Plugin Registry
    "PluginRegistry",
    # Domain Router
    "DomainRouter",
    "DomainRouterConfig",
    "CircuitState",
    # Modular Orchestrator
    "ModularOrchestrator",
    "try_modular_execution",
    "get_modular_stats",
]
