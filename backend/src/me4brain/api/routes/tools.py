"""Tools API Routes.

Espone i tool di Me4BrAIn tramite API REST per integrazioni esterne:
- Search: Ricerca semantica per intent
- List: Lista paginata dei tool disponibili
- Get: Dettagli singolo tool
- Execute: Esecuzione tool con argomenti
- Categories: Categorie disponibili
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from me4brain.api.middleware.api_key import get_optional_api_key
from me4brain.config import get_settings
from me4brain.embeddings import get_embedding_service
from me4brain.engine.hybrid_router.constants import CAPABILITIES_COLLECTION
from me4brain.memory.procedural import Tool, get_procedural_memory
from me4brain.retrieval.tool_executor import (
    ExecutionRequest,
    create_tool_executor,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/tools", tags=["Tools"])


# =============================================================================
# Request/Response Models
# =============================================================================


class ToolSearchRequest(BaseModel):
    """Richiesta di ricerca tool per intent."""

    query: str = Field(
        ..., min_length=1, max_length=1000, description="Intent in linguaggio naturale"
    )
    limit: int = Field(default=10, ge=1, le=50, description="Numero massimo di risultati")
    categories: list[str] = Field(
        default_factory=list, description="Filtro per categorie (opzionale)"
    )
    min_score: float = Field(default=0.3, ge=0.0, le=1.0, description="Score minimo per inclusione")


class ToolSearchResult(BaseModel):
    """Singolo risultato della ricerca tool."""

    tool_id: str
    name: str
    description: str
    score: float
    category: str = ""
    endpoint: str | None = None
    method: str = "POST"


class ToolSearchResponse(BaseModel):
    """Risposta ricerca tool."""

    query: str
    results: list[ToolSearchResult]
    total: int


class ToolListResponse(BaseModel):
    """Risposta lista paginata tool."""

    tools: list[ToolSearchResult]
    total: int
    limit: int
    offset: int


class ToolDetailResponse(BaseModel):
    """Dettagli completi di un tool."""

    id: str
    name: str
    description: str
    endpoint: str | None = None
    method: str = "POST"
    status: str = "ACTIVE"
    version: str = "1.0"
    api_schema: dict[str, Any] = Field(default_factory=dict)
    success_rate: float = 0.5
    avg_latency_ms: float = 0.0
    total_calls: int = 0


class ToolExecuteRequest(BaseModel):
    """Richiesta di esecuzione tool."""

    tool_id: str = Field(..., description="ID del tool da eseguire")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Argomenti per il tool")
    intent: str = Field(default="", description="Descrizione dell'intento (per Muscle Memory)")
    use_cache: bool = Field(default=True, description="Usa Muscle Memory cache")


class ToolExecuteResponse(BaseModel):
    """Risposta esecuzione tool."""

    success: bool
    tool_id: str
    tool_name: str
    result: Any | None = None
    error: str | None = None
    latency_ms: float = 0.0
    cached: bool = False


class CategoryInfo(BaseModel):
    """Info su una categoria."""

    name: str
    tool_count: int


class CategoriesResponse(BaseModel):
    """Lista categorie disponibili."""

    categories: list[CategoryInfo]
    total_tools: int


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/search",
    response_model=ToolSearchResponse,
    summary="Search Tools",
    description="Cerca tool usando ricerca semantica per intent.",
)
async def search_tools(
    request: ToolSearchRequest,
    api_key: str | None = Depends(get_optional_api_key),
) -> ToolSearchResponse:
    """Ricerca semantica di tool per intent."""
    settings = get_settings()
    tenant_id = settings.default_tenant_id

    try:
        # Embedding dell'intent
        embedding_service = get_embedding_service()
        query_embedding = embedding_service.embed_query(request.query)

        # Cerca nel Skill Graph (Qdrant-first, fallback KuzuDB)
        procedural = get_procedural_memory()
        tools_with_scores = await procedural.find_tools_for_intent(
            tenant_id=tenant_id,
            intent_embedding=query_embedding,
            top_k=request.limit,
            min_weight=request.min_score,
        )

        results = []
        for tool, score in tools_with_scores:
            # Filtra per categoria se specificata
            tool_category = _extract_category(tool.name)
            if request.categories and tool_category not in request.categories:
                continue

            results.append(
                ToolSearchResult(
                    tool_id=tool.id,
                    name=tool.name,
                    description=tool.description[:200] if tool.description else "",
                    score=score,
                    category=tool_category,
                    endpoint=tool.endpoint,
                    method=tool.method,
                )
            )

        logger.info(
            "tools_search_completed",
            query=request.query[:50],
            results_count=len(results),
        )

        return ToolSearchResponse(
            query=request.query,
            results=results,
            total=len(results),
        )

    except Exception as e:
        logger.error("tools_search_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {e}",
        )


@router.get(
    "/list",
    response_model=ToolListResponse,
    summary="List Tools",
    description="Lista paginata di tutti i tool disponibili.",
)
async def list_tools(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: str = Query(default="ACTIVE", description="Filtra per status"),
    api_key: str | None = Depends(get_optional_api_key),
) -> ToolListResponse:
    """Lista paginata di tool da Qdrant."""
    try:
        from qdrant_client import QdrantClient

        settings = get_settings()
        client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_http_port)

        # Scroll all tools from Qdrant
        all_tools = []
        scroll_result, _ = client.scroll(
            collection_name=CAPABILITIES_COLLECTION,
            limit=1000,  # Max tools
            with_payload=True,
        )

        for point in scroll_result:
            payload = point.payload or {}
            # Filtra per status if present
            if payload.get("status", "ACTIVE") != status_filter:
                continue

            # tool_catalog usa tool_name e domain invece di name e category
            tool_name = payload.get("tool_name", payload.get("name", ""))
            domain = payload.get("domain", "")

            all_tools.append(
                ToolSearchResult(
                    tool_id=str(point.id),
                    name=tool_name,
                    description=payload.get("description", "")[:200],
                    score=0.5,  # No score in list
                    category=domain or _extract_category(tool_name),
                    endpoint=payload.get("endpoint"),
                    method=payload.get("method", "POST"),
                )
            )

        # Paginazione
        total = len(all_tools)
        paginated = all_tools[offset : offset + limit]

        return ToolListResponse(
            tools=paginated,
            total=total,
            limit=limit,
            offset=offset,
        )

    except Exception as e:
        logger.error("tools_list_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"List failed: {e}",
        )


@router.post(
    "/execute",
    response_model=ToolExecuteResponse,
    summary="Execute Tool",
    description="Esegue un tool con i parametri specificati.",
)
async def execute_tool(
    request: ToolExecuteRequest,
    api_key: str | None = Depends(get_optional_api_key),
) -> ToolExecuteResponse:
    """Esegue un tool."""
    settings = get_settings()
    tenant_id = settings.default_tenant_id
    user_id = "api_user"  # In produzione, estratto da auth

    executor = create_tool_executor()

    try:
        exec_request = ExecutionRequest(
            tenant_id=tenant_id,
            user_id=user_id,
            intent=request.intent or f"Execute {request.tool_id}",
            tool_id=request.tool_id,
            arguments=request.arguments,
        )

        result = await executor.execute(
            request=exec_request,
            use_muscle_memory=request.use_cache,
        )

        return ToolExecuteResponse(
            success=result.success,
            tool_id=result.tool_id,
            tool_name=result.tool_name,
            result=result.result,
            error=result.error,
            latency_ms=result.latency_ms,
            cached=result.from_muscle_memory,
        )

    except Exception as e:
        logger.error("tool_execute_failed", tool_id=request.tool_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Execution failed: {e}",
        )
    finally:
        await executor.close()


@router.get(
    "/categories",
    response_model=CategoriesResponse,
    summary="List Categories",
    description="Lista le categorie di tool disponibili.",
)
async def list_categories(
    api_key: str | None = Depends(get_optional_api_key),
) -> CategoriesResponse:
    """Lista categorie con conteggio tool da Qdrant."""
    try:
        from qdrant_client import QdrantClient

        settings = get_settings()
        client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_http_port)

        # Scroll all tools from Qdrant
        scroll_result, _ = client.scroll(
            collection_name=CAPABILITIES_COLLECTION,
            limit=1000,
            with_payload=True,
        )

        # Conta tool per categoria
        category_counts: dict[str, int] = {}
        total = 0

        for point in scroll_result:
            payload = point.payload or {}
            tool_name = payload.get("tool_name", payload.get("name", ""))
            # Usa domain come categoria
            category = payload.get("domain", _extract_category(tool_name))
            category_counts[category] = category_counts.get(category, 0) + 1
            total += 1

        categories = [
            CategoryInfo(name=name, tool_count=count)
            for name, count in sorted(category_counts.items(), key=lambda x: -x[1])
        ]

        return CategoriesResponse(categories=categories, total_tools=total)

        return CategoriesResponse(
            categories=categories,
            total_tools=total,
        )

    except Exception as e:
        logger.error("categories_list_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Categories failed: {e}",
        )


# NOTE: /{tool_id} DEVE essere l'ultima route GET per evitare conflitti
# con route statiche come /categories, /list
@router.get(
    "/{tool_id}",
    response_model=ToolDetailResponse,
    summary="Get Tool",
    description="Ottiene i dettagli completi di un tool.",
)
async def get_tool(
    tool_id: str,
    api_key: str | None = Depends(get_optional_api_key),
) -> ToolDetailResponse:
    """Dettagli di un singolo tool - cerca in Qdrant."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    settings = get_settings()

    try:
        qdrant = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_http_port,
        )

        # Cerca per tool_id come point ID (UUID)
        try:
            # Prima prova a recuperare per ID diretto (se è un UUID valido)
            points = qdrant.retrieve(
                collection_name=CAPABILITIES_COLLECTION,
                ids=[tool_id],
                with_payload=True,
            )
        except Exception:
            points = []

        # Se non trovato per ID, cerca per nome
        if not points:
            results, _ = qdrant.scroll(
                collection_name=CAPABILITIES_COLLECTION,
                scroll_filter=Filter(
                    must=[FieldCondition(key="name", match=MatchValue(value=tool_id))]
                ),
                limit=1,
                with_payload=True,
            )
            points = results

        if not points:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tool not found: {tool_id}",
            )

        point = points[0]
        payload = point.payload or {}
        tool_name = payload.get("tool_name", payload.get("name", ""))

        return ToolDetailResponse(
            id=str(point.id),
            name=tool_name,
            description=payload.get("description", ""),
            endpoint=payload.get("endpoint"),
            method=payload.get("method", "POST"),
            status=payload.get("status", "ACTIVE"),
            version=payload.get("version", "1.0"),
            api_schema=payload.get("schema_json", {}),
            success_rate=payload.get("success_rate", 0.5),
            avg_latency_ms=payload.get("avg_latency_ms", 0.0),
            total_calls=payload.get("total_calls", 0),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("tool_get_failed", tool_id=tool_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Get failed: {e}",
        )


# =============================================================================
# Helpers
# =============================================================================


def _extract_category(tool_name: str) -> str:
    """Estrae la categoria dal nome del tool.

    Convenzione: tool_name = "category_action" → category
    Esempio: "coingecko_price" → "coingecko"
    """
    if "_" in tool_name:
        return tool_name.split("_")[0]
    return "general"


# =============================================================================
# OpenAPI Registration
# =============================================================================


class RegisterToolFromOpenAPIRequest(BaseModel):
    """Richiesta di registrazione tool da OpenAPI spec."""

    openapi_url: str | None = Field(
        default=None, description="URL dello spec OpenAPI (fetch remoto)"
    )
    openapi_spec: dict[str, Any] | None = Field(
        default=None, description="OpenAPI spec inline (alternativo a url)"
    )
    domain: str = Field(..., min_length=1, description="Dominio di appartenenza")
    auth_config: dict[str, Any] = Field(
        default_factory=dict, description="Configurazione auth per le API"
    )
    prefix: str = Field(default="", description="Prefisso da aggiungere ai nomi tool")


class RegisteredToolInfo(BaseModel):
    """Info su un tool registrato."""

    tool_id: str
    name: str
    endpoint: str
    method: str


class RegisterToolsResponse(BaseModel):
    """Risposta registrazione tool."""

    success: bool
    domain: str
    registered_tools: list[RegisteredToolInfo]
    total: int
    errors: list[str] = Field(default_factory=list)


@router.post(
    "/register",
    response_model=RegisterToolsResponse,
    summary="Register Tools from OpenAPI",
    description="Registra dinamicamente tool da una specifica OpenAPI.",
)
async def register_tools_from_openapi(
    request: RegisterToolFromOpenAPIRequest,
    api_key: str | None = Depends(get_optional_api_key),
) -> RegisterToolsResponse:
    """Registra tool da OpenAPI spec.

    Flow:
    1. Fetch/parse OpenAPI spec
    2. Extract endpoints come tools
    3. Generate embeddings per descriptions
    4. Sync in Qdrant (procedural memory)
    """
    import httpx

    settings = get_settings()
    tenant_id = settings.default_tenant_id
    errors: list[str] = []

    # 1. Ottieni spec
    if request.openapi_url:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(request.openapi_url)
                response.raise_for_status()
                spec = response.json()
        except Exception as e:
            return RegisterToolsResponse(
                success=False,
                domain=request.domain,
                registered_tools=[],
                total=0,
                errors=[f"Failed to fetch OpenAPI spec: {e}"],
            )
    elif request.openapi_spec:
        spec = request.openapi_spec
    else:
        return RegisterToolsResponse(
            success=False,
            domain=request.domain,
            registered_tools=[],
            total=0,
            errors=["Either openapi_url or openapi_spec must be provided"],
        )

    # 2. Estrai endpoints
    paths = spec.get("paths", {})
    servers = spec.get("servers", [{"url": ""}])
    base_url = servers[0].get("url", "") if servers else ""

    registered_tools: list[RegisteredToolInfo] = []
    procedural = get_procedural_memory()
    embedding_service = get_embedding_service()

    for path, methods in paths.items():
        for method, details in methods.items():
            if method.upper() not in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                continue

            # Crea tool name
            operation_id = details.get("operationId", "")
            if operation_id:
                tool_name = f"{request.prefix}{operation_id}" if request.prefix else operation_id
            else:
                # Genera da path
                path_parts = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
                tool_name = f"{request.prefix}{request.domain}_{method}_{path_parts}"

            description = details.get("summary", "") or details.get("description", "")
            if not description:
                description = f"{method.upper()} {path}"

            # Crea tool
            tool = Tool(
                name=tool_name,
                description=description[:500],
                tenant_id=tenant_id,
                endpoint=f"{base_url}{path}",
                method=method.upper(),
                api_schema={
                    "parameters": details.get("parameters", []),
                    "requestBody": details.get("requestBody", {}),
                    "responses": details.get("responses", {}),
                    "auth_config": request.auth_config,
                },
            )

            try:
                # Registra in Neo4j
                tool_id = await procedural.register_tool(tool)

                # Indicizza in Qdrant
                tool_embedding = embedding_service.embed_document(f"{tool_name}: {description}")
                await procedural.index_tool_in_qdrant(tool, tool_embedding)

                registered_tools.append(
                    RegisteredToolInfo(
                        tool_id=tool_id,
                        name=tool_name,
                        endpoint=f"{base_url}{path}",
                        method=method.upper(),
                    )
                )

                logger.info(
                    "tool_registered_from_openapi",
                    tool_name=tool_name,
                    endpoint=f"{base_url}{path}",
                )

            except Exception as e:
                errors.append(f"Failed to register {tool_name}: {e}")

    return RegisterToolsResponse(
        success=len(registered_tools) > 0,
        domain=request.domain,
        registered_tools=registered_tools,
        total=len(registered_tools),
        errors=errors,
    )
