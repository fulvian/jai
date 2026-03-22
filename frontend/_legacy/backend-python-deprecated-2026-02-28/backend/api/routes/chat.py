"""Chat endpoints with SSE streaming - Tool Calling Engine Integration.

Usa il nuovo Tool Calling Engine per query in linguaggio naturale.
"""

import json
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.models.chat import ChatRequest
from backend.services.me4brain_service import get_me4brain_service

router = APIRouter()


class ToolCallRequest(BaseModel):
    """Request for direct tool call."""

    tool_name: str = Field(..., min_length=1, description="Nome del tool")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Argomenti")
    session_id: str | None = Field(None, description="Session ID opzionale")


class ToolCallResponse(BaseModel):
    """Response from direct tool call."""

    tool_name: str
    success: bool
    result: Any | None = None
    error: str | None = None
    latency_ms: float = 0


@router.post("/chat")
async def chat_stream(request: ChatRequest):
    """
    SSE streaming chat endpoint powered by Tool Calling Engine.

    Flow:
    1. Create/use session
    2. Add user turn to local session
    3. Execute query via Tool Calling Engine
    4. Stream response chunks via SSE
    5. Add assistant turn to session

    Returns:
        StreamingResponse with SSE chunks.
    """
    me4brain = get_me4brain_service()
    session_id = request.session_id

    # Create session if not provided
    if not session_id:
        session_data = await me4brain.create_session()
        session_id = session_data["session_id"]

    # Add user message to session
    await me4brain.add_turn(session_id, role="user", content=request.message)

    async def event_generator():
        full_response = ""
        tools_used: list[dict[str, Any]] = []

        # Send session_id first
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

        try:
            async for chunk in me4brain.query_stream(
                query=request.message,
                session_id=session_id,
            ):
                chunk_type = chunk.get("type", "content")

                if chunk_type == "start":
                    # Session started
                    pass

                elif chunk_type == "status":
                    # Status update
                    status_content = chunk.get("content", "")
                    if status_content:
                        yield f"data: {json.dumps({'type': 'status', 'content': status_content})}\n\n"

                elif chunk_type == "content":
                    # Main content token
                    content = chunk.get("content", "")
                    if content:
                        full_response += content
                        yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"

                elif chunk_type == "thinking":
                    # Thinking event (streaming thought tokens)
                    thinking_content = chunk.get("content", "")
                    if thinking_content:
                        payload = {
                            "type": "thinking",
                            "content": thinking_content,
                            "icon": "🤔",
                        }
                        thinking_msg = chunk.get("message")
                        if thinking_msg:
                            payload["message"] = thinking_msg
                        yield f"data: {json.dumps(payload)}\n\n"

                elif chunk_type == "tool":
                    # Tool call result
                    tool_call = chunk.get("tool_call", {})
                    tools_used.append(tool_call)
                    yield f"data: {json.dumps({'type': 'tool', 'tool_name': tool_call.get('tool'), 'tool_result': tool_call})}\n\n"

                elif chunk_type == "done":
                    # Stream complete
                    latency = chunk.get("latency_ms", 0)
                    yield f"data: {json.dumps({'type': 'metadata', 'latency_ms': latency, 'tools_count': len(tools_used)})}\n\n"

                elif chunk_type == "error":
                    error_msg = chunk.get("error", "Unknown error")
                    yield f"data: {json.dumps({'type': 'error', 'error': error_msg})}\n\n"

            # Save assistant response to session
            if full_response:
                await me4brain.add_turn(session_id, role="assistant", content=full_response)

            # Signal completion
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            error_msg = str(e)
            print(f"Error in chat stream: {error_msg}")
            yield f"data: {json.dumps({'type': 'error', 'error': error_msg})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",  # Allow all origins (or specify frontend URL)
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Accept",
            "X-Accel-Buffering": "no",  # Nginx: disable buffering for SSE
        },
    )


@router.post("/chat/simple")
async def chat_simple(request: ChatRequest) -> dict[str, Any]:
    """
    Non-streaming chat endpoint for simple queries.

    Returns full response as JSON.
    """
    me4brain = get_me4brain_service()
    session_id = request.session_id

    if not session_id:
        session_data = await me4brain.create_session()
        session_id = session_data["session_id"]

    # Add user message
    await me4brain.add_turn(session_id, role="user", content=request.message)

    try:
        # Execute query via Tool Calling Engine
        response = await me4brain.query(
            query=request.message,
            include_raw_results=True,
        )

        # Add assistant response
        await me4brain.add_turn(session_id, role="assistant", content=response.answer)

        return {
            "session_id": session_id,
            "message": response.answer,
            "tools_used": [
                {
                    "name": t.tool_name,
                    "success": t.success,
                    "latency_ms": t.latency_ms,
                }
                for t in response.tools_called
            ],
            "total_latency_ms": response.total_latency_ms,
            "raw_results": response.raw_results,
        }

    except Exception as e:
        return {
            "session_id": session_id,
            "message": "",
            "error": str(e),
            "tools_used": [],
        }


@router.post("/chat/tool")
async def call_tool_direct(request: ToolCallRequest) -> ToolCallResponse:
    """
    Direct tool call endpoint.

    Bypasses LLM routing and calls a tool directly.
    """
    import time

    me4brain = get_me4brain_service()
    start = time.perf_counter()

    try:
        result = await me4brain.call_tool(request.tool_name, **request.arguments)
        latency = (time.perf_counter() - start) * 1000

        return ToolCallResponse(
            tool_name=request.tool_name,
            success=True,
            result=result,
            latency_ms=latency,
        )

    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return ToolCallResponse(
            tool_name=request.tool_name,
            success=False,
            error=str(e),
            latency_ms=latency,
        )


@router.get("/chat/sessions")
async def list_sessions(user_id: str = "default") -> dict[str, Any]:
    """List chat sessions for a user."""
    me4brain = get_me4brain_service()
    sessions = await me4brain.list_sessions(user_id=user_id)
    return {"sessions": sessions, "user_id": user_id}


@router.get("/chat/sessions/{session_id}")
async def get_session(session_id: str, max_turns: int = 50) -> dict[str, Any]:
    """Get session context (conversation history)."""
    me4brain = get_me4brain_service()
    context = await me4brain.get_session_context(session_id, max_turns=max_turns)
    return context


@router.post("/chat/sessions")
async def create_session(user_id: str = "default") -> dict[str, Any]:
    """Create a new chat session."""
    me4brain = get_me4brain_service()
    session = await me4brain.create_session(user_id=user_id)
    return session


@router.delete("/chat/sessions/{session_id}")
async def delete_session(session_id: str, user_id: str = "default") -> dict[str, str]:
    """Delete a chat session."""
    me4brain = get_me4brain_service()
    await me4brain.delete_session(session_id, user_id=user_id)
    return {"status": "deleted", "session_id": session_id}


class UpdateSessionRequest(BaseModel):
    title: str


@router.patch("/chat/sessions/{session_id}")
async def update_session(
    session_id: str,
    request: UpdateSessionRequest,
    user_id: str = "default",
) -> dict[str, Any]:
    """Update session title."""
    me4brain = get_me4brain_service()
    success = await me4brain.update_session_title(session_id, request.title, user_id=user_id)
    if success:
        return {"status": "updated", "session_id": session_id, "title": request.title}
    return {"status": "failed", "session_id": session_id}


@router.put("/chat/sessions/{session_id}/config")
async def update_session_config(
    session_id: str,
    config: dict,
    user_id: str = "default",
) -> dict[str, Any]:
    """Update session configuration."""
    me4brain = get_me4brain_service()
    # TODO: Implementare update config in me4brain_service
    return {"status": "updated", "session_id": session_id, "config": config}


@router.delete("/chat/sessions/{session_id}/turns/{turn_index}")
async def delete_session_turn(
    session_id: str,
    turn_index: int,
    user_id: str = "default",
) -> dict[str, Any]:
    """Delete a specific turn from session."""
    me4brain = get_me4brain_service()
    # TODO: Implementare delete turn in me4brain_service
    return {"status": "deleted", "session_id": session_id, "turn_index": turn_index}


@router.put("/chat/sessions/{session_id}/turns/{turn_index}")
async def update_session_turn(
    session_id: str,
    turn_index: int,
    content: str,
    user_id: str = "default",
) -> dict[str, Any]:
    """Update a specific turn and re-execute query."""
    me4brain = get_me4brain_service()
    # TODO: Implementare update turn con re-execution
    return {"status": "updated", "session_id": session_id, "turn_index": turn_index}


@router.post("/chat/sessions/{session_id}/retry/{turn_index}")
async def retry_session_turn(
    session_id: str,
    turn_index: int,
    user_id: str = "default",
):
    """Retry a query from a specific turn."""
    me4brain = get_me4brain_service()
    # TODO: Implementare retry con SSE streaming
    # Questo deve restituire StreamingResponse come /chat
    pass
