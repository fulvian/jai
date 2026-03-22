"""Tool Calling Engine - Core module for LLM-based tool orchestration.

This module provides a clean, modular engine for:
1. Routing natural language queries to appropriate tools
2. Executing tools in parallel with error handling
3. Synthesizing tool results into coherent responses

Architecture: Router → Executor → Synthesizer

Example:
    from me4brain.engine import ToolCallingEngine

    engine = await ToolCallingEngine.create()
    response = await engine.run("Prezzo Bitcoin e meteo Roma")
    print(response.answer)
"""

from me4brain.engine.types import (
    EngineResponse,
    ToolDefinition,
    ToolResult,
    ToolTask,
)
from me4brain.engine.catalog import ToolCatalog
from me4brain.engine.router import ToolRouter
from me4brain.engine.executor import ParallelExecutor
from me4brain.engine.synthesizer import ResponseSynthesizer
from me4brain.engine.core import ToolCallingEngine

__all__ = [
    # Types
    "ToolDefinition",
    "ToolTask",
    "ToolResult",
    "EngineResponse",
    # Components
    "ToolCatalog",
    "ToolRouter",
    "ParallelExecutor",
    "ResponseSynthesizer",
    # Main Engine
    "ToolCallingEngine",
]
