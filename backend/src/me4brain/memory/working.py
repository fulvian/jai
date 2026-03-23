"""Working Memory - Short Term Memory Layer.

Implementa il Layer I del sistema cognitivo:
- Redis Streams per log conversazione (TTFT <1ms)
- NetworkX per grafo effimero di sessione (coreferenze)
- Compressione zlib+pickle per serializzazione efficiente
- Sessioni categorizzate: free, topic, template
"""

import json
import pickle
import zlib
from datetime import UTC, datetime
from typing import Any, Literal

import networkx as nx
import redis.asyncio as redis
import structlog

from me4brain.config import get_settings

logger = structlog.get_logger(__name__)


class WorkingMemory:
    """Gestisce la memoria a breve termine (STM).

    Architettura ibrida:
    - Redis Streams: log immutabile dei turni di conversazione
    - NetworkX: grafo effimero per relazioni di sessione
    """

    # Costanti
    MAX_STREAM_LENGTH = 100  # Max messaggi per stream
    SESSION_TTL_SECONDS = 86400  # 24 ore
    COMPRESSION_LEVEL = 6  # zlib (1-9, 6 è buon compromesso)

    def __init__(self, redis_client: redis.Redis | None = None) -> None:
        """Inizializza Working Memory.

        Args:
            redis_client: Client Redis opzionale (per testing/DI)
        """
        self._redis: redis.Redis | None = redis_client
        self._session_graphs: dict[str, nx.DiGraph] = {}

    async def get_redis(self) -> redis.Redis:
        """Lazy initialization del client Redis."""
        if self._redis is None:
            settings = get_settings()
            self._redis = redis.from_url(
                settings.redis_url,
                decode_responses=False,  # Binary per pickle
            )
        return self._redis

    # -------------------------------------------------------------------------
    # Key Generation (Multi-Tenant)
    # -------------------------------------------------------------------------

    @staticmethod
    def _stream_key(tenant_id: str, user_id: str, session_id: str) -> str:
        """Genera chiave Redis per lo stream di messaggi."""
        return f"tenant:{tenant_id}:user:{user_id}:session:{session_id}:stream"

    @staticmethod
    def _graph_key(tenant_id: str, user_id: str, session_id: str) -> str:
        """Genera chiave Redis per il grafo serializzato."""
        return f"tenant:{tenant_id}:user:{user_id}:session:{session_id}:graph"

    @staticmethod
    def _session_id(tenant_id: str, user_id: str, session_id: str) -> str:
        """Genera ID univoco per la sessione."""
        return f"{tenant_id}:{user_id}:{session_id}"

    @staticmethod
    def _meta_key(tenant_id: str, user_id: str, session_id: str) -> str:
        """Genera chiave Redis per i metadati della sessione."""
        return f"tenant:{tenant_id}:user:{user_id}:session:{session_id}:meta"

    @staticmethod
    def _sessions_index_key(tenant_id: str, user_id: str) -> str:
        """Genera chiave Redis per l'indice delle sessioni utente."""
        return f"tenant:{tenant_id}:user:{user_id}:sessions:index"

    @staticmethod
    def _feedback_key(tenant_id: str, user_id: str, session_id: str) -> str:
        """Genera chiave Redis per i feedback della sessione."""
        return f"tenant:{tenant_id}:user:{user_id}:session:{session_id}:feedback"

    # -------------------------------------------------------------------------
    # Message Stream (Redis Streams)
    # -------------------------------------------------------------------------

    async def add_message(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Aggiunge un messaggio allo stream della sessione.

        Args:
            tenant_id: ID del tenant
            user_id: ID dell'utente
            session_id: ID della sessione
            role: Ruolo (human, ai, system, tool)
            content: Contenuto del messaggio
            metadata: Metadati opzionali

        Returns:
            ID del messaggio nello stream
        """
        r = await self.get_redis()
        key = self._stream_key(tenant_id, user_id, session_id)

        # Prepara payload
        payload = {
            b"role": role.encode(),
            b"content": content.encode(),
            b"timestamp": datetime.now(UTC).isoformat().encode(),
        }

        if metadata:
            payload[b"metadata"] = self._compress(metadata)

        # Aggiungi allo stream con MAXLEN per evitare crescita infinita
        message_id = await r.xadd(
            key,
            payload,
            maxlen=self.MAX_STREAM_LENGTH,
            approximate=True,
        )

        # Imposta TTL sulla chiave
        await r.expire(key, self.SESSION_TTL_SECONDS)

        logger.debug(
            "stm_message_added",
            tenant_id=tenant_id,
            session_id=session_id,
            role=role,
            message_id=message_id,
        )

        return message_id.decode() if isinstance(message_id, bytes) else str(message_id)

    async def delete_message(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
        message_id: str,
    ) -> bool:
        """Elimina un messaggio dallo stream della sessione.

        Args:
            tenant_id: ID del tenant
            user_id: ID dell'utente
            session_id: ID della sessione
            message_id: ID del messaggio nello stream (es. '1707594000000-0')

        Returns:
            True se eliminato con successo
        """
        r = await self.get_redis()
        key = self._stream_key(tenant_id, user_id, session_id)

        deleted_count = await r.xdel(key, message_id)

        # Remove any associated feedback
        feedback_key = self._feedback_key(tenant_id, user_id, session_id)
        await r.hdel(feedback_key, message_id)

        logger.debug(
            "stm_message_deleted",
            tenant_id=tenant_id,
            session_id=session_id,
            message_id=message_id,
            deleted=deleted_count > 0,
        )

        return deleted_count > 0

    async def update_feedback(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
        message_id: str,
        score: int,
        comment: str | None = None,
    ) -> bool:
        """Aggiorna il feedback per un messaggio.

        Usa un Redis Hash separato (stream entries sono immutabili).

        Args:
            tenant_id: ID del tenant
            user_id: ID dell'utente
            session_id: ID della sessione
            message_id: ID del messaggio nello stream
            score: +1 (upvote) o -1 (downvote), 0 per rimuovere
            comment: Commento opzionale

        Returns:
            True se aggiornato con successo
        """
        r = await self.get_redis()
        feedback_key = self._feedback_key(tenant_id, user_id, session_id)

        if score == 0:
            # Remove feedback (toggle off)
            await r.hdel(feedback_key, message_id)
        else:
            import json

            value = json.dumps({"score": score, "comment": comment or ""})
            await r.hset(feedback_key, message_id, value)

        # Set same TTL as session
        await r.expire(feedback_key, self.SESSION_TTL_SECONDS)

        logger.debug(
            "stm_feedback_updated",
            session_id=session_id,
            message_id=message_id,
            score=score,
        )

        return True

    async def get_feedback(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
    ) -> dict[str, dict[str, Any]]:
        """Recupera tutti i feedback per una sessione.

        Returns:
            Dict {message_id: {score, comment}}
        """
        import json

        r = await self.get_redis()
        feedback_key = self._feedback_key(tenant_id, user_id, session_id)

        raw = await r.hgetall(feedback_key)
        if not isinstance(raw, dict):
            return {}
        result: dict[str, dict[str, Any]] = {}

        for k, v in raw.items():
            key_str = k.decode() if isinstance(k, bytes) else k
            val_str = v.decode() if isinstance(v, bytes) else v
            try:
                result[key_str] = json.loads(val_str)
            except (json.JSONDecodeError, TypeError):
                result[key_str] = {"score": 0, "comment": ""}

        return result

    async def get_messages(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
        count: int = 20,
    ) -> list[dict[str, Any]]:
        """Recupera gli ultimi N messaggi dalla sessione.

        Args:
            tenant_id: ID del tenant
            user_id: ID dell'utente
            session_id: ID della sessione
            count: Numero di messaggi da recuperare

        Returns:
            Lista di messaggi con id, role, content, timestamp, feedback_score
        """
        r = await self.get_redis()
        key = self._stream_key(tenant_id, user_id, session_id)

        # XREVRANGE: ultimi N messaggi (ordine cronologico inverso)
        raw_messages = await r.xrevrange(key, count=count)

        # Load feedback scores for this session
        feedback = await self.get_feedback(tenant_id, user_id, session_id)

        messages = []
        for msg_id, data in reversed(raw_messages):  # Ripristina ordine cronologico
            mid = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
            msg: dict[str, Any] = {
                "id": mid,
                "role": data.get(b"role", b"").decode(),
                "content": data.get(b"content", b"").decode(),
                "timestamp": data.get(b"timestamp", b"").decode(),
            }

            if b"metadata" in data:
                msg["metadata"] = self._decompress(data[b"metadata"])

            # Merge feedback score if present
            fb = feedback.get(mid)
            if fb:
                msg["feedback_score"] = fb.get("score", 0)
                msg["feedback_comment"] = fb.get("comment", "")

            messages.append(msg)

        return messages

    # -------------------------------------------------------------------------
    # Ephemeral Knowledge Graph (NetworkX)
    # -------------------------------------------------------------------------

    def get_session_graph(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
    ) -> nx.DiGraph:
        """Ottiene il grafo della sessione (crea se non esiste).

        Il grafo è mantenuto in memoria per performance.
        Viene serializzato in Redis periodicamente per persistenza.
        """
        sid = self._session_id(tenant_id, user_id, session_id)

        if sid not in self._session_graphs:
            self._session_graphs[sid] = nx.DiGraph()
            logger.debug("stm_graph_created", session=sid)

        return self._session_graphs[sid]

    def add_entity(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
        entity_id: str,
        entity_type: str,
        label: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Aggiunge un'entità al grafo di sessione.

        Args:
            entity_id: ID univoco dell'entità
            entity_type: Tipo (Person, Project, Document, etc.)
            label: Nome visualizzato
            properties: Proprietà aggiuntive
        """
        graph = self.get_session_graph(tenant_id, user_id, session_id)

        graph.add_node(
            entity_id,
            type=entity_type,
            label=label,
            created_at=datetime.now(UTC).isoformat(),
            **(properties or {}),
        )

        logger.debug(
            "stm_entity_added",
            entity_id=entity_id,
            entity_type=entity_type,
        )

    def add_relation(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
        source_id: str,
        target_id: str,
        relation_type: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Aggiunge una relazione tra entità nel grafo.

        Args:
            source_id: ID entità sorgente
            target_id: ID entità target
            relation_type: Tipo di relazione (FOCUS_ON, MENTIONS, etc.)
            properties: Proprietà della relazione
        """
        graph = self.get_session_graph(tenant_id, user_id, session_id)

        graph.add_edge(
            source_id,
            target_id,
            type=relation_type,
            created_at=datetime.now(UTC).isoformat(),
            **(properties or {}),
        )

        logger.debug(
            "stm_relation_added",
            source=source_id,
            target=target_id,
            relation=relation_type,
        )

    def resolve_reference(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
        reference: str,
        entity_type: str | None = None,
    ) -> str | None:
        """Risolve un riferimento ambiguo (es. "lui", "il progetto").

        Cerca nel grafo l'entità più recente del tipo specificato
        o con relazione FOCUS_ON attiva.

        Args:
            reference: Il riferimento da risolvere
            entity_type: Tipo di entità da cercare (opzionale)

        Returns:
            ID dell'entità risolta o None
        """
        graph = self.get_session_graph(tenant_id, user_id, session_id)

        # Cerca nodi con relazione FOCUS_ON (contesto attivo)
        focus_nodes = [
            (u, v, d) for u, v, d in graph.edges(data=True) if d.get("type") == "FOCUS_ON"
        ]

        if focus_nodes:
            # Prendi il più recente
            focus_nodes.sort(key=lambda x: x[2].get("created_at", ""), reverse=True)
            _, target, _ = focus_nodes[0]

            if entity_type is None:
                return target

            # Verifica tipo
            node_data = graph.nodes.get(target, {})
            if node_data.get("type") == entity_type:
                return target

        # Fallback: cerca per tipo
        if entity_type:
            candidates = [(n, d) for n, d in graph.nodes(data=True) if d.get("type") == entity_type]

            if candidates:
                # Prendi il più recente
                candidates.sort(key=lambda x: x[1].get("created_at", ""), reverse=True)
                return candidates[0][0]

        return None

    # -------------------------------------------------------------------------
    # Persistence (Compressione zlib + pickle)
    # -------------------------------------------------------------------------

    def _compress(self, data: Any) -> bytes:
        """Comprime dati con zlib + pickle."""
        pickled = pickle.dumps(data)
        return zlib.compress(pickled, level=self.COMPRESSION_LEVEL)

    def _decompress(self, data: bytes) -> Any:
        """Decomprime dati da zlib + pickle."""
        decompressed = zlib.decompress(data)
        return pickle.loads(decompressed)  # noqa: S301

    async def persist_graph(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
    ) -> None:
        """Persiste il grafo di sessione su Redis.

        Usato per backup e per ripristino dopo restart.
        """
        sid = self._session_id(tenant_id, user_id, session_id)

        if sid not in self._session_graphs:
            return

        graph = self._session_graphs[sid]
        r = await self.get_redis()
        key = self._graph_key(tenant_id, user_id, session_id)

        # Serializza grafo
        compressed = self._compress(nx.node_link_data(graph))
        await r.set(key, compressed, ex=self.SESSION_TTL_SECONDS)

        logger.debug(
            "stm_graph_persisted",
            session=sid,
            nodes=graph.number_of_nodes(),
            edges=graph.number_of_edges(),
            size_bytes=len(compressed),
        )

    async def load_graph(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
    ) -> nx.DiGraph | None:
        """Carica un grafo di sessione da Redis.

        Returns:
            Il grafo caricato o None se non esiste
        """
        r = await self.get_redis()
        key = self._graph_key(tenant_id, user_id, session_id)

        data = await r.get(key)
        if data is None:
            return None

        graph_data = self._decompress(data)
        graph = nx.node_link_graph(graph_data, directed=True)

        # Cache in memoria
        sid = self._session_id(tenant_id, user_id, session_id)
        self._session_graphs[sid] = graph

        logger.debug(
            "stm_graph_loaded",
            session=sid,
            nodes=graph.number_of_nodes(),
            edges=graph.number_of_edges(),
        )

        return graph

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------

    async def clear_session(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
    ) -> None:
        """Pulisce completamente una sessione (stream + graph + meta)."""
        r = await self.get_redis()
        sid = self._session_id(tenant_id, user_id, session_id)

        # Rimuovi da Redis
        stream_key = self._stream_key(tenant_id, user_id, session_id)
        graph_key = self._graph_key(tenant_id, user_id, session_id)
        meta_key = self._meta_key(tenant_id, user_id, session_id)
        index_key = self._sessions_index_key(tenant_id, user_id)

        await r.delete(stream_key, graph_key, meta_key)
        await r.srem(index_key, session_id)

        # Rimuovi da memoria
        self._session_graphs.pop(sid, None)

        logger.info("stm_session_cleared", session=sid)

    # -------------------------------------------------------------------------
    # Session Metadata Management
    # -------------------------------------------------------------------------

    async def register_session(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
        title: str | None = None,
        session_type: Literal["free", "topic", "template"] = "free",
        topic: str | None = None,
        tags: list[str] | None = None,
        prompts: list[dict[str, Any]] | None = None,
        schedule: str | None = None,
    ) -> None:
        """Registra una nuova sessione nell'indice e crea i metadati.

        Args:
            tenant_id: ID del tenant
            user_id: ID dell'utente
            session_id: ID della sessione
            title: Titolo opzionale della sessione
            session_type: Tipo sessione (free, topic, template)
            topic: Argomento (solo per topic sessions)
            tags: Tags di categorizzazione (solo per topic sessions)
            prompts: Prompt predefiniti (solo per template sessions)
            schedule: Cron expression (solo per template sessions)
        """
        r = await self.get_redis()
        index_key = self._sessions_index_key(tenant_id, user_id)
        meta_key = self._meta_key(tenant_id, user_id, session_id)

        # Aggiungi all'indice sessioni
        await r.sadd(index_key, session_id)

        # Crea metadati iniziali
        now = datetime.now(UTC).isoformat()
        metadata: dict[str, str] = {
            "session_id": session_id,
            "title": title or "",
            "created_at": now,
            "updated_at": now,
            "session_type": session_type,
        }

        # Campi specifici per tipo
        if topic is not None:
            metadata["topic"] = topic
        if tags is not None:
            metadata["tags"] = json.dumps(tags)
        if prompts is not None:
            metadata["prompts"] = json.dumps(prompts)
        if schedule is not None:
            metadata["schedule"] = schedule

        await r.hset(meta_key, mapping=metadata)
        await r.expire(meta_key, self.SESSION_TTL_SECONDS)
        await r.expire(index_key, self.SESSION_TTL_SECONDS)

        logger.debug(
            "session_registered",
            session_id=session_id,
            title=title,
            session_type=session_type,
        )

    async def update_session_metadata(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
        title: str | None = None,
        session_type: Literal["free", "topic", "template"] | None = None,
        topic: str | None = None,
        tags: list[str] | None = None,
        prompts: list[dict[str, Any]] | None = None,
        schedule: str | None = None,
    ) -> bool:
        """Aggiorna i metadati di una sessione.

        Args:
            tenant_id: ID del tenant
            user_id: ID dell'utente
            session_id: ID della sessione
            title: Nuovo titolo (opzionale)
            session_type: Tipo sessione (opzionale)
            topic: Argomento (opzionale, solo per topic sessions)
            tags: Tags (opzionale, solo per topic sessions)
            prompts: Prompt predefiniti (opzionale, solo per template sessions)
            schedule: Cron expression (opzionale, solo per template sessions)

        Returns:
            True se aggiornato con successo
        """
        r = await self.get_redis()
        meta_key = self._meta_key(tenant_id, user_id, session_id)

        # Verifica che la sessione esista
        exists = await r.exists(meta_key)
        if not exists:
            # Crea metadati se non esistono (retrocompatibilità)
            await self.register_session(tenant_id, user_id, session_id, title)
            return True

        # Aggiorna metadati
        updates: dict[str, str] = {"updated_at": datetime.now(UTC).isoformat()}
        if title is not None:
            updates["title"] = title
        if session_type is not None:
            updates["session_type"] = session_type
        if topic is not None:
            updates["topic"] = topic
        if tags is not None:
            updates["tags"] = json.dumps(tags)
        if prompts is not None:
            updates["prompts"] = json.dumps(prompts)
        if schedule is not None:
            updates["schedule"] = schedule

        await r.hset(meta_key, mapping=updates)

        logger.debug("session_metadata_updated", session_id=session_id, title=title)
        return True

    async def get_session_metadata(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
    ) -> dict[str, Any] | None:
        """Recupera i metadati di una sessione.

        Returns:
            Dict con metadati o None se non esiste.
            I campi tags e prompts vengono deserializzati da JSON.
        """
        r = await self.get_redis()
        meta_key = self._meta_key(tenant_id, user_id, session_id)

        data = await r.hgetall(meta_key)
        if not data:
            return None

        # Decodifica bytes
        result: dict[str, Any] = {
            k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
            for k, v in data.items()
        }

        # Deserializza campi JSON (tags, prompts)
        for json_field in ("tags", "prompts"):
            if json_field in result and isinstance(result[json_field], str):
                try:
                    result[json_field] = json.loads(result[json_field])
                except json.JSONDecodeError:
                    result[json_field] = []

        # Default session_type per retrocompatibilità
        if "session_type" not in result:
            result["session_type"] = "free"

        return result

    async def list_sessions(
        self,
        tenant_id: str,
        user_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Elenca le sessioni utente con metadati.

        Args:
            tenant_id: ID del tenant
            user_id: ID dell'utente
            limit: Numero massimo di sessioni

        Returns:
            Lista di sessioni con metadati
        """
        r = await self.get_redis()
        index_key = self._sessions_index_key(tenant_id, user_id)

        # Recupera tutti gli ID sessione dall'indice
        session_ids = await r.smembers(index_key)

        sessions = []
        for sid in session_ids:
            session_id = sid.decode() if isinstance(sid, bytes) else sid
            meta = await self.get_session_metadata(tenant_id, user_id, session_id)

            if meta:
                # Conta messaggi nello stream
                stream_key = self._stream_key(tenant_id, user_id, session_id)
                msg_count = await r.xlen(stream_key)

                session_data: dict[str, Any] = {
                    "session_id": session_id,
                    "title": meta.get("title", ""),
                    "created_at": meta.get("created_at"),
                    "updated_at": meta.get("updated_at"),
                    "message_count": msg_count,
                    "session_type": meta.get("session_type", "free"),
                }

                # Includi campi specifici per tipo
                if meta.get("topic"):
                    session_data["topic"] = meta["topic"]
                if meta.get("tags"):
                    session_data["tags"] = meta["tags"]
                if meta.get("prompts"):
                    session_data["prompts"] = meta["prompts"]
                if meta.get("schedule"):
                    session_data["schedule"] = meta["schedule"]

                sessions.append(session_data)

        # Ordina per data creazione (più recente prima)
        sessions.sort(
            key=lambda x: x.get("created_at", ""),
            reverse=True,
        )

        return sessions[:limit]

    async def close(self) -> None:
        """Chiude le connessioni."""
        if self._redis:
            await self._redis.close()


# Singleton instance
_working_memory: WorkingMemory | None = None


def get_working_memory() -> WorkingMemory:
    """Ottiene l'istanza singleton di WorkingMemory."""
    global _working_memory
    if _working_memory is None:
        _working_memory = WorkingMemory()
    return _working_memory
