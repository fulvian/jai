"""Browser Manager - Pool e lifecycle management sessioni browser."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

import structlog
from redis.asyncio import Redis

from me4brain.core.browser.types import (
    BrowserConfig,
    BrowserSession,
    BrowserStatus,
)

logger = structlog.get_logger(__name__)


class BrowserManager:
    """
    Manager per pool di sessioni browser.

    Responsabilità:
    - Creazione/distruzione sessioni
    - Pool management con limiti
    - Persistenza stato in Redis
    - Resource cleanup
    """

    PREFIX = "me4brain:browser:sessions"
    INDEX_KEY = "me4brain:browser:session_index"
    DEFAULT_MAX_SESSIONS = 5

    def __init__(
        self,
        redis: Redis | None = None,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        default_config: BrowserConfig | None = None,
    ):
        """
        Inizializza manager.

        Args:
            redis: Client Redis per persistenza
            max_sessions: Max sessioni concurrent
            default_config: Config default per nuove sessioni
        """
        self.redis = redis
        self.max_sessions = max_sessions
        self.default_config = default_config or BrowserConfig()

        # In-memory session registry (browser contexts non serializzabili)
        self._sessions: dict[str, BrowserSessionWrapper] = {}
        self._lock = asyncio.Lock()

    def _session_key(self, session_id: str) -> str:
        """Genera chiave Redis per sessione."""
        return f"{self.PREFIX}:{session_id}"

    async def create_session(
        self,
        config: BrowserConfig | None = None,
        start_url: str | None = None,
    ) -> BrowserSession:
        """
        Crea nuova sessione browser.

        Args:
            config: Configurazione browser
            start_url: URL iniziale

        Returns:
            Sessione creata

        Raises:
            RuntimeError: Se limite sessioni raggiunto
        """
        async with self._lock:
            # Check limiti
            active = await self.count_active()
            if active >= self.max_sessions:
                raise RuntimeError(
                    f"Max sessions reached ({self.max_sessions}). Close existing sessions first."
                )

            session_id = str(uuid.uuid4())[:12]
            session_config = config or self.default_config

            session = BrowserSession(
                id=session_id,
                config=session_config,
                status=BrowserStatus.CREATING,
            )

            # Salva metadata in Redis
            if self.redis:
                await self.redis.set(
                    self._session_key(session_id),
                    session.model_dump_json(),
                )
                await self.redis.sadd(self.INDEX_KEY, session_id)

            logger.info(
                "browser_session_creating",
                session_id=session_id,
                headless=session_config.headless,
                start_url=start_url,
            )

            # Crea wrapper con browser reale (lazy)
            from me4brain.core.browser.session import BrowserSessionWrapper

            wrapper = BrowserSessionWrapper(session)
            self._sessions[session_id] = wrapper

            # Inizializza browser
            try:
                await wrapper.initialize()

                if start_url:
                    await wrapper.navigate(start_url)

                session.status = BrowserStatus.READY
                await self._update_session(session)

                logger.info(
                    "browser_session_ready",
                    session_id=session_id,
                    url=session.current_url,
                )

            except Exception as e:
                session.status = BrowserStatus.ERROR
                await self._update_session(session)
                logger.error("browser_session_error", error=str(e))
                raise

            return session

    async def get_session(self, session_id: str) -> BrowserSession | None:
        """
        Recupera metadata sessione.

        Args:
            session_id: ID sessione

        Returns:
            Sessione o None
        """
        if self.redis:
            data = await self.redis.get(self._session_key(session_id))
            if data:
                return BrowserSession.model_validate_json(data)

        # Fallback: in-memory
        wrapper = self._sessions.get(session_id)
        if wrapper:
            return wrapper.session

        return None

    async def get_wrapper(self, session_id: str) -> BrowserSessionWrapper | None:
        """
        Recupera wrapper con browser context.

        Args:
            session_id: ID sessione

        Returns:
            Wrapper o None
        """
        return self._sessions.get(session_id)

    async def close_session(self, session_id: str) -> bool:
        """
        Chiude sessione browser.

        Args:
            session_id: ID sessione

        Returns:
            True se chiusa
        """
        wrapper = self._sessions.pop(session_id, None)
        if wrapper:
            try:
                await wrapper.close()
            except Exception as e:
                logger.warning("browser_close_error", error=str(e))

        if self.redis:
            await self.redis.srem(self.INDEX_KEY, session_id)
            await self.redis.delete(self._session_key(session_id))

        logger.info("browser_session_closed", session_id=session_id)
        return True

    async def list_sessions(self) -> list[BrowserSession]:
        """Lista sessioni attive."""
        sessions = []

        if self.redis:
            session_ids = await self.redis.smembers(self.INDEX_KEY)
            for sid in session_ids:
                session = await self.get_session(sid)
                if session:
                    sessions.append(session)
        else:
            for wrapper in self._sessions.values():
                sessions.append(wrapper.session)

        return sessions

    async def count_active(self) -> int:
        """Conta sessioni attive."""
        if self.redis:
            return await self.redis.scard(self.INDEX_KEY)
        return len(self._sessions)

    async def _update_session(self, session: BrowserSession) -> None:
        """Aggiorna sessione in Redis."""
        if self.redis:
            await self.redis.set(
                self._session_key(session.id),
                session.model_dump_json(),
            )

    async def cleanup_stale(self, max_age_seconds: int = 3600) -> int:
        """
        Pulisce sessioni vecchie.

        Args:
            max_age_seconds: Max età in secondi

        Returns:
            Numero sessioni pulite
        """
        cleaned = 0
        now = datetime.now()

        sessions = await self.list_sessions()
        for session in sessions:
            age = (now - session.created_at).total_seconds()
            if age > max_age_seconds:
                await self.close_session(session.id)
                cleaned += 1

        if cleaned > 0:
            logger.info("browser_sessions_cleaned", count=cleaned)

        return cleaned

    async def close_all(self) -> int:
        """Chiude tutte le sessioni."""
        sessions = list(self._sessions.keys())
        for sid in sessions:
            await self.close_session(sid)
        return len(sessions)


# Singleton
_browser_manager: BrowserManager | None = None


def get_browser_manager() -> BrowserManager | None:
    """Ottiene manager globale."""
    return _browser_manager


def set_browser_manager(manager: BrowserManager) -> None:
    """Imposta manager globale."""
    global _browser_manager
    _browser_manager = manager


async def initialize_browser_manager(
    redis_url: str = "redis://localhost:6379",
    max_sessions: int = 5,
) -> BrowserManager:
    """Inizializza browser manager."""
    redis = Redis.from_url(redis_url, decode_responses=True)
    manager = BrowserManager(redis=redis, max_sessions=max_sessions)
    set_browser_manager(manager)
    logger.info("browser_manager_initialized", max_sessions=max_sessions)
    return manager
