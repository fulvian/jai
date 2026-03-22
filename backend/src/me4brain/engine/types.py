"""Type definitions for the Tool Calling Engine.

Pydantic models for:
- Tool definitions (schema for LLM)
- Tool tasks (what the LLM decides to execute)
- Tool results (execution outcomes)
- Engine responses (final output)
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolParameter(BaseModel):
    """Schema for a single tool parameter."""

    type: str = Field(
        default="string",
        description="JSON Schema type (string, number, boolean, array, object)",
    )
    description: str = Field(
        default="",
        description="Human-readable description for the LLM",
    )
    required: bool = Field(
        default=False,
        description="Whether this parameter is required",
    )
    default: Any = Field(
        default=None,
        description="Default value if not provided",
    )
    enum: list[str] | None = Field(
        default=None,
        description="Allowed values for enum parameters",
    )
    items: dict[str, str] | None = Field(
        default=None,
        description="Item schema for array types (e.g., {'type': 'string'})",
    )


class ToolDefinition(BaseModel):
    """Definition of a tool exposed to the LLM.

    This is used to:
    1. Generate OpenAI-compatible function schemas
    2. Validate arguments before execution
    3. Document tool capabilities
    """

    name: str = Field(
        ...,
        description="Unique tool name (e.g., 'coingecko_price')",
    )
    description: str = Field(
        ...,
        description="Clear description of what the tool does - shown to LLM",
    )
    parameters: dict[str, ToolParameter | dict[str, Any]] = Field(
        default_factory=dict,
        description="Tool parameters with JSON Schema types",
    )
    domain: str | None = Field(
        default=None,
        description="Domain this tool belongs to (e.g., 'finance_crypto')",
    )
    category: str | None = Field(
        default=None,
        description="Functional category (e.g., 'price', 'search', 'weather')",
    )

    def to_openai_function(self) -> dict[str, Any]:
        """Convert to OpenAI-compatible function schema.

        Returns:
            Dict ready for use in 'tools' parameter of chat completions.
        """
        # Build parameters schema
        properties = {}
        required = []

        for param_name, param_info in self.parameters.items():
            if isinstance(param_info, ToolParameter):
                prop: dict[str, Any] = {
                    "type": param_info.type,
                    "description": param_info.description,
                }
                if param_info.enum:
                    prop["enum"] = param_info.enum
                # CRITICAL: array type MUST have items defined for valid JSON Schema
                if param_info.type == "array":
                    prop["items"] = param_info.items or {"type": "string"}
                properties[param_name] = prop

                if param_info.required:
                    required.append(param_name)
            else:
                # Already a dict (legacy format)
                properties[param_name] = param_info
                if param_info.get("required"):
                    required.append(param_name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


class ToolTask(BaseModel):
    """A tool execution task decided by the LLM.

    Created by the Router after analyzing the user query.
    Contains everything needed to execute the tool.
    """

    tool_name: str = Field(
        ...,
        description="Name of the tool to execute",
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments for the tool call",
    )
    reasoning: str | None = Field(
        default=None,
        description="Optional: why the LLM chose this tool",
    )
    call_id: str | None = Field(
        default=None,
        description="Unique ID for this tool call (from LLM)",
    )


class ToolResult(BaseModel):
    """Result of executing a single tool.

    Contains success/failure status and either data or error.
    """

    tool_name: str = Field(
        ...,
        description="Name of the executed tool",
    )
    success: bool = Field(
        ...,
        description="Whether execution succeeded",
    )
    data: dict[str, Any] | None = Field(
        default=None,
        description="Tool output data if successful",
    )
    error: str | None = Field(
        default=None,
        description="Error message if failed",
    )
    latency_ms: float = Field(
        default=0.0,
        description="Execution time in milliseconds",
    )
    call_id: str | None = Field(
        default=None,
        description="Unique ID matching the ToolTask",
    )


class EngineResponse(BaseModel):
    """Complete response from the Tool Calling Engine.

    Contains:
    - Final synthesized answer
    - All tool results
    - Optional reasoning trace
    """

    answer: str = Field(
        ...,
        description="Natural language response synthesized from tool results",
    )
    tool_results: list[ToolResult] = Field(
        default_factory=list,
        description="Results from all executed tools",
    )
    reasoning_trace: list[str] | None = Field(
        default=None,
        description="Optional trace of LLM reasoning steps",
    )
    tools_called: list[str] = Field(
        default_factory=list,
        description="Names of tools that were called",
    )
    total_latency_ms: float = Field(
        default=0.0,
        description="Total engine execution time",
    )


class StreamChunk(BaseModel):
    """Chunk of data yielded during streaming execution.
    
    Used to transport both reasoning/thinking tokens and final answer content.
    """

    type: str = Field(..., description="'thinking' or 'content'")
    content: str | None = Field(default=None, description="Final answer content token")
    thinking: str | None = Field(default=None, description="Thinking/reasoning token")
    session_id: str | None = Field(default=None, description="Session identifier")
    phase: str | None = Field(default=None, description="Execution phase (e.g., 'synthesis')")
    icon: str | None = Field(default=None, description="UI icon suggestion")
