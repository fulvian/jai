"""Me4BrAIn API - FastAPI Application.

Entry point principale per l'API Gateway.
"""

# FIX Issue #3: nest_asyncio REMOVED in production.
# It breaks event loop invariants under concurrent SSE streams.
# LlamaIndex sync reranker calls now use run_in_executor() instead.
# If you see "This event loop is already running" errors, the fix is to
# wrap the offending sync call in asyncio.get_event_loop().run_in_executor(None, sync_fn)
# instead of re-enabling nest_asyncio.
import structlog as _structlog

_nest_logger = _structlog.get_logger("nest_asyncio_guard")
_nest_logger.info(
    "nest_asyncio_disabled",
    reason="Prevents deadlocks under concurrent SSE. Sync calls use run_in_executor.",
)

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from me4brain import __version__
from me4brain.api.routes import (
    admin,
    backup,
    clawhub_skills,
    cognitive,
    diagnostics,
    domains,
    engine,
    health,
    ingestion,
    memory,
    semantic,
    session_graph,
    skills,
    tools,
    working,
    procedural,
    llm_config,
    monitoring,
    providers,
)
from me4brain.api.routes import providers


from me4brain.config import get_settings
from me4brain.utils.logging import configure_logging

# Configurazione logger
logger = structlog.get_logger(__name__)


async def _verify_llm_connectivity() -> None:
    """Verify LLM provider is reachable and required model is loaded.

    This check runs at startup to detect configuration issues early.
    """
    try:
        from me4brain.llm.health import get_llm_health_checker
        from me4brain.llm.config import get_llm_config

        config = get_llm_config()
        checker = get_llm_health_checker()

        # Check Ollama with required model
        ollama_result = await checker.check_ollama(
            config.ollama_base_url, required_model=config.model_routing
        )

        if not ollama_result.healthy:
            logger.warning(
                "startup_llm_check_failed",
                provider="ollama",
                error=ollama_result.error,
                required_model=config.model_routing,
                hint=f"Run: ollama pull {config.model_routing}",
            )
            # Don't fail startup, but log prominently for debugging
        else:
            logger.info(
                "startup_llm_check_passed",
                provider="ollama",
                model=config.model_routing,
                latency_ms=ollama_result.latency_ms,
            )
    except Exception as e:
        logger.warning(
            "startup_llm_check_error",
            error=str(e),
            note="LLM connectivity check skipped - will retry on first query",
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifecycle manager per l'applicazione.

    Gestisce startup e shutdown delle risorse.
    """
    settings = get_settings()
    configure_logging(settings.log_level)

    logger.info(
        "me4brain_starting",
        version=__version__,
        host=settings.host,
        port=settings.port,
        debug=settings.debug,
    )

    # Inizializza servizi
    from me4brain.memory import get_episodic_memory, get_semantic_memory

    # Inizializza Semantic Memory (Neo4j schema)
    semantic = get_semantic_memory()
    await semantic.initialize()

    # Inizializza Session Knowledge Graph (Neo4j schema per sessioni)
    from me4brain.memory.session_graph import get_session_graph

    session_kg = get_session_graph()
    await session_kg.initialize_schema()

    # Inizializza Procedural Memory (Qdrant collection + Tool Sync)
    from me4brain.memory.procedural import get_procedural_memory

    procedural = get_procedural_memory()
    await procedural.initialize()

    # Inizializza Episodic Memory (Qdrant collection)
    episodic = get_episodic_memory()
    await episodic.initialize()

    # Inizializza Plugin Registry per i domini
    from me4brain.core.plugin_registry import PluginRegistry

    await PluginRegistry.get_instance("default")

    # Set startup time per health checks
    from me4brain.api.routes.health import set_startup_time

    set_startup_time()

    # Verify LLM connectivity at startup
    await _verify_llm_connectivity()

    # Inizializza Browser Manager per browser automation
    browser_manager = None
    try:
        from me4brain.core.browser.manager import initialize_browser_manager

        browser_manager = await initialize_browser_manager(
            redis_url=settings.redis_url,
            max_sessions=5,
        )
        logger.info("browser_manager_initialized")
    except Exception as e:
        logger.warning("browser_manager_init_failed", error=str(e))

    logger.info("me4brain_services_initialized")

    # Register MCP tools dynamically
    try:
        from me4brain.api.mcp import register_dynamic_tools

        await register_dynamic_tools()
        logger.info("mcp_dynamic_tools_registered")
    except Exception as e:
        logger.warning("mcp_dynamic_registration_failed", error=str(e))

    yield

    # Cleanup
    logger.info("me4brain_shutting_down")

    # Chiudi sessioni browser
    if browser_manager:
        await browser_manager.close_all()

    # Chiudi connessioni
    await semantic.close()
    await episodic.close()


def create_app() -> FastAPI:
    """Factory per creare l'applicazione FastAPI."""
    settings = get_settings()

    # OpenAPI Tags con descrizioni
    openapi_tags = [
        {"name": "Health", "description": "Health checks e status del sistema"},
        {
            "name": "Memory",
            "description": "API principale per gestione memoria (episodic, query)",
        },
        {
            "name": "Cognitive",
            "description": "Query cognitive con ciclo completo di ragionamento",
        },
        {
            "name": "Semantic Memory",
            "description": "Gestione entità e relazioni nel knowledge graph",
        },
        {
            "name": "Procedural Memory",
            "description": "Gestione tool e skill registrati",
        },
        {
            "name": "Working Memory",
            "description": "Memoria di lavoro e sessioni utente",
        },
        {"name": "Tools", "description": "Esecuzione tool e interrogazione catalogo"},
        {
            "name": "Engine",
            "description": "Tool Calling Engine - Query NL → tool selection → execution → synthesis",
        },
        {
            "name": "domains",
            "description": "Dispatch query a domain handlers specializzati",
        },
        {"name": "Admin", "description": "Amministrazione sistema e statistiche"},
        {"name": "Backup & DR", "description": "Backup, restore e disaster recovery"},
    ]

    app = FastAPI(
        title="Me4BrAIn Core",
        description="""
## Piattaforma Universale di Memoria Agentica API-First

Me4BrAIn Core fornisce un sistema di memoria a lungo termine per agenti AI, 
ispirato ai sistemi di memoria umana:

- **Memoria Episodica**: Eventi e esperienze passate
- **Memoria Semantica**: Knowledge graph di entità e relazioni
- **Memoria Procedurale**: Tool e skill appresi
- **Memoria di Lavoro**: Contesto sessione corrente

### Autenticazione
Usa header `X-Tenant-ID` e `X-User-ID` per multi-tenancy.
        """,
        version=__version__,
        openapi_tags=openapi_tags,
        docs_url="/docs",  # Sempre disponibile
        redoc_url="/redoc",  # Sempre disponibile
        openapi_url="/openapi.json",  # Sempre disponibile
        contact={
            "name": "Me4BrAIn Team",
            "url": "https://github.com/fulvian/me4brain",
        },
        license_info={
            "name": "MIT",
            "url": "https://opensource.org/licenses/MIT",
        },
        lifespan=lifespan,
    )

    # CORS Middleware
    # Configurable via ME4BRAIN_CORS_ORIGINS env var (comma-separated list)
    cors_origins_str = settings.cors_origins.strip()
    if settings.debug:
        allow_origins = ["*"]
    elif cors_origins_str:
        allow_origins = [o.strip() for o in cors_origins_str.split(",") if o.strip()]
    else:
        allow_origins = []

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate Limiting
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from me4brain.api.middleware.rate_limit import limiter

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Audit Logging Middleware
    from me4brain.api.middleware.audit import AuditLogMiddleware

    app.add_middleware(AuditLogMiddleware)

    # Universal Guardrails Middleware
    # Applica adaptive guardrails a TUTTE le risposte API
    from me4brain.api.middleware.guardrails import UniversalGuardrailsMiddleware

    app.add_middleware(UniversalGuardrailsMiddleware)

    # Routes
    app.include_router(health.router)
    app.include_router(memory.router, prefix="/v1")
    app.include_router(admin.router, prefix="/v1")
    app.include_router(tools.router, prefix="/v1")
    app.include_router(engine.router, prefix="/v1")
    app.include_router(domains.router, prefix="/v1")
    app.include_router(working.router, prefix="/v1")
    app.include_router(procedural.router, prefix="/v1")
    app.include_router(semantic.router, prefix="/v1")
    app.include_router(backup.router, prefix="/v1")
    app.include_router(cognitive.router, prefix="/v1")
    app.include_router(session_graph.router, prefix="/v1")
    app.include_router(session_graph.prompt_router, prefix="/v1")
    app.include_router(clawhub_skills.router, prefix="/v1")
    app.include_router(skills.router, prefix="/v1")
    app.include_router(diagnostics.router)  # Phase 5: Diagnostics endpoint
    app.include_router(ingestion.router)
    app.include_router(llm_config.router)
    app.include_router(monitoring.router)
    app.include_router(providers.router)
    logger.info("skills_router_included", file=getattr(skills, "__file__", "N/A"))

    # Mount MCP Server (SSE Transport for LM Studio)
    try:
        from me4brain.api.mcp import mcp

        # FastMCP v3: explicitly set path to avoid default overrides and ensure /mcp/sse
        mcp_app = mcp.http_app(transport="sse", path="/sse")
        app.mount("/mcp", mcp_app)
        logger.info("mcp_server_mounted", path="/mcp")
    except Exception as e:
        logger.warning("mcp_server_mount_failed", error=str(e))

    return app


# Istanza applicazione per uvicorn
app = create_app()


def main() -> None:
    """Entry point per esecuzione diretta."""
    import uvicorn

    settings = get_settings()

    uvicorn.run(
        "me4brain.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
        loop="asyncio",
    )


if __name__ == "__main__":
    main()
