"""Cognitive API Routes.

Endpoints per funzionalità cognitive avanzate:
- Reason: multi-step reasoning con chain-of-thought
- Plan: generazione piani strutturati
"""

from typing import Any
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from me4brain.api.middleware.auth import AuthenticatedUser, get_current_user_dev
from me4brain.api.middleware.rate_limit import RATE_LIMITS, limiter
from me4brain.config import get_settings
from me4brain.core import run_cognitive_cycle
from me4brain.llm.nanogpt import NanoGPTClient
from me4brain.utils.metrics import track_latency

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/cognitive", tags=["Cognitive"])


# =============================================================================
# Request/Response Models
# =============================================================================


class ReasonRequest(BaseModel):
    """Richiesta per multi-step reasoning."""

    query: str = Field(..., min_length=1, max_length=10000)
    context: list[dict[str, Any]] = Field(default_factory=list)
    max_steps: int = Field(default=5, ge=1, le=10)


class ReasoningStepResponse(BaseModel):
    """Singolo step di ragionamento."""

    step: int
    action: str
    description: str
    duration_ms: float = 0.0


class ReasonResponse(BaseModel):
    """Risposta reasoning con trace completo."""

    response: str
    confidence: float
    reasoning_steps: list[ReasoningStepResponse]
    sources: list[str] = Field(default_factory=list)
    session_id: str
    thread_id: str


class PlanRequest(BaseModel):
    """Richiesta per generazione piano."""

    goal: str = Field(..., min_length=1, max_length=1000)
    constraints: list[str] = Field(default_factory=list)


class PlanStep(BaseModel):
    """Singolo step del piano."""

    step_number: int
    action: str
    description: str
    dependencies: list[int] = Field(default_factory=list)


class PlanResponse(BaseModel):
    """Risposta con piano strutturato."""

    goal: str
    plan: list[PlanStep]
    constraints_applied: list[str]
    total_steps: int


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/reason", response_model=ReasonResponse)
@limiter.limit(RATE_LIMITS["cognitive"])
@track_latency("POST", "/cognitive/reason", "default")
async def reason(
    request: Request,
    reason_request: ReasonRequest,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> ReasonResponse:
    """Esegue multi-step reasoning con chain-of-thought.

    Utilizza il ciclo cognitivo con trace completo del ragionamento.
    """
    session_id = str(uuid4())
    thread_id = str(uuid4())

    # Esegue ciclo cognitivo
    final_state = await run_cognitive_cycle(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        session_id=session_id,
        user_input=reason_request.query,
    )

    # Estrai reasoning steps
    reasoning_trace = final_state.get("reasoning_trace", [])
    reasoning_steps = []
    for i, step in enumerate(reasoning_trace):
        reasoning_steps.append(
            ReasoningStepResponse(
                step=i + 1,
                action=step.get("action", "reasoning"),
                description=step.get("description", step.get("thought", "")),
                duration_ms=step.get("duration_ms", 0.0),
            )
        )

    return ReasonResponse(
        response=final_state.get("final_response", ""),
        confidence=final_state.get("confidence", 0.5),
        reasoning_steps=reasoning_steps,
        sources=final_state.get("sources_used", []),
        session_id=session_id,
        thread_id=thread_id,
    )


@router.post("/plan", response_model=PlanResponse)
@limiter.limit(RATE_LIMITS["cognitive"])
@track_latency("POST", "/cognitive/plan", "default")
async def plan(
    request: Request,
    plan_request: PlanRequest,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> PlanResponse:
    """Genera un piano strutturato per raggiungere un obiettivo.

    Utilizza LLM per decomporre l'obiettivo in step azionabili.
    """
    settings = get_settings()
    llm_client = NanoGPTClient(
        api_key=getattr(settings, "NANOGPT_API_KEY", ""),
        base_url=getattr(settings, "NANOGPT_BASE_URL", "https://nano-gpt.com/api"),
    )

    # Costruisci prompt per planning
    constraints_text = ""
    if plan_request.constraints:
        constraints_text = "\n\nConstraints to consider:\n" + "\n".join(
            f"- {c}" for c in plan_request.constraints
        )

    planning_prompt = f"""You are a planning assistant. Create a detailed step-by-step plan to achieve the following goal.

Goal: {plan_request.goal}{constraints_text}

Respond with a JSON array of steps, where each step has:
- step_number: integer starting from 1
- action: short action name (e.g., "research", "implement", "test")
- description: detailed description of what to do
- dependencies: list of step_numbers this step depends on (empty if no dependencies)

Example format:
[
  {{"step_number": 1, "action": "research", "description": "Research existing solutions", "dependencies": []}},
  {{"step_number": 2, "action": "design", "description": "Design the architecture", "dependencies": [1]}}
]

Respond ONLY with the JSON array, no other text."""

    try:
        response = await llm_client.complete(
            prompt=planning_prompt,
            model="mistralai/mistral-large-3-675b-instruct-2512",
            max_tokens=2000,
            temperature=0.3,
        )

        # Parse JSON response
        import json
        import re

        # Estrai JSON dalla risposta
        content = response.get("content", "[]")

        # Rimuovi markdown code blocks se presenti
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
        if json_match:
            content = json_match.group(1)

        # Trova array JSON
        array_match = re.search(r"\[[\s\S]*\]", content)
        if array_match:
            content = array_match.group(0)

        steps_data = json.loads(content)
        plan_steps = []
        for step_data in steps_data:
            plan_steps.append(
                PlanStep(
                    step_number=step_data.get("step_number", len(plan_steps) + 1),
                    action=step_data.get("action", "step"),
                    description=step_data.get("description", ""),
                    dependencies=step_data.get("dependencies", []),
                )
            )

    except Exception as e:
        logger.warning("plan_generation_fallback", error=str(e))
        # Fallback: piano semplice
        plan_steps = [
            PlanStep(
                step_number=1,
                action="analyze",
                description=f"Analyze the goal: {plan_request.goal}",
                dependencies=[],
            ),
            PlanStep(
                step_number=2,
                action="execute",
                description="Execute the necessary actions to achieve the goal",
                dependencies=[1],
            ),
            PlanStep(
                step_number=3,
                action="verify",
                description="Verify that the goal has been achieved",
                dependencies=[2],
            ),
        ]

    return PlanResponse(
        goal=plan_request.goal,
        plan=plan_steps,
        constraints_applied=plan_request.constraints,
        total_steps=len(plan_steps),
    )
