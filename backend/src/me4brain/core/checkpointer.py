"""PostgreSQL Checkpointer per LangGraph.

Wrapper per langgraph-checkpoint-postgres con configurazione
specifica per Me4BrAIn.
"""

import structlog
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from me4brain.config import get_settings

logger = structlog.get_logger(__name__)


async def create_checkpointer() -> AsyncPostgresSaver:
    """Crea e inizializza il checkpointer PostgreSQL.

    Il checkpointer persiste lo stato del grafo LangGraph
    per durabilità e ripresa delle conversazioni.

    Returns:
        AsyncPostgresSaver configurato e inizializzato
    """
    settings = get_settings()

    # Crea checkpointer con connection string
    checkpointer = AsyncPostgresSaver.from_conn_string(settings.postgres_dsn)

    # Setup schema (crea tabelle se non esistono)
    await checkpointer.setup()

    logger.info(
        "checkpointer_initialized",
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
    )

    return checkpointer


# Global checkpointer instance
_checkpointer: AsyncPostgresSaver | None = None


async def get_checkpointer() -> AsyncPostgresSaver:
    """Ottiene l'istanza singleton del checkpointer.

    Lazy initialization: il checkpointer viene creato
    solo al primo utilizzo.
    """
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = await create_checkpointer()
    return _checkpointer


async def close_checkpointer() -> None:
    """Chiude la connessione del checkpointer."""
    global _checkpointer
    if _checkpointer is not None:
        # AsyncPostgresSaver non ha un metodo close esplicito,
        # ma il pool viene gestito automaticamente
        _checkpointer = None
        logger.info("checkpointer_closed")
