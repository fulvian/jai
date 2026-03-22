"""OpenAPI Ingestion - Zero-Shot Tool Registration.

Parser automatico per OpenAPI 3.x che genera nodi :Tool
nel Skill Graph senza configurazione manuale.
"""

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog
from pydantic import BaseModel, Field

from me4brain.embeddings import get_embedding_service
from me4brain.memory.procedural import ProceduralMemory, Tool, get_procedural_memory

logger = structlog.get_logger(__name__)


class OpenAPIEndpoint(BaseModel):
    """Rappresenta un endpoint estratto da OpenAPI."""

    path: str
    method: str
    operation_id: str | None = None
    summary: str | None = None
    description: str | None = None
    parameters: list[dict[str, Any]] = Field(default_factory=list)
    request_body: dict[str, Any] | None = None
    responses: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class OpenAPISpec(BaseModel):
    """Rappresenta una specifica OpenAPI parsata."""

    title: str
    version: str
    description: str | None = None
    base_url: str | None = None
    endpoints: list[OpenAPIEndpoint] = Field(default_factory=list)


class OpenAPIIngester:
    """Ingester per specifiche OpenAPI.

    Parsa file OpenAPI 3.x e registra automaticamente
    i tool nel Procedural Memory (Skill Graph + Qdrant).
    """

    def __init__(
        self,
        procedural_memory: ProceduralMemory | None = None,
    ) -> None:
        """Inizializza l'ingester.

        Args:
            procedural_memory: ProceduralMemory da usare (default: singleton)
        """
        self._procedural = procedural_memory

    def get_procedural(self) -> ProceduralMemory:
        """Ottiene ProceduralMemory."""
        if self._procedural is None:
            self._procedural = get_procedural_memory()
        return self._procedural

    def parse_openapi(self, spec: dict[str, Any]) -> OpenAPISpec:
        """Parsa una specifica OpenAPI in struttura interna.

        Args:
            spec: Dizionario JSON della specifica OpenAPI

        Returns:
            OpenAPISpec con tutti gli endpoint estratti
        """
        # Estrai info generali
        info = spec.get("info", {})
        title = info.get("title", "Unknown API")
        version = info.get("version", "1.0.0")
        description = info.get("description")

        # Estrai base URL da servers
        servers = spec.get("servers", [])
        base_url = servers[0].get("url") if servers else None

        # Estrai endpoints
        endpoints = []
        paths = spec.get("paths", {})

        for path, path_item in paths.items():
            # Ignora riferimenti e parametri di path
            if path.startswith("$"):
                continue

            for method in ["get", "post", "put", "patch", "delete", "options", "head"]:
                if method not in path_item:
                    continue

                operation = path_item[method]

                endpoint = OpenAPIEndpoint(
                    path=path,
                    method=method.upper(),
                    operation_id=operation.get("operationId"),
                    summary=operation.get("summary"),
                    description=operation.get("description"),
                    parameters=operation.get("parameters", []),
                    request_body=operation.get("requestBody"),
                    responses=operation.get("responses", {}),
                    tags=operation.get("tags", []),
                )

                endpoints.append(endpoint)

        logger.info(
            "openapi_parsed",
            title=title,
            version=version,
            endpoints_count=len(endpoints),
        )

        return OpenAPISpec(
            title=title,
            version=version,
            description=description,
            base_url=base_url,
            endpoints=endpoints,
        )

    def _generate_tool_name(self, endpoint: OpenAPIEndpoint) -> str:
        """Genera un nome human-readable per il tool."""
        if endpoint.operation_id:
            # Converti camelCase/snake_case in spazi
            name = endpoint.operation_id
            # CamelCase -> spazi
            import re

            name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
            # snake_case -> spazi
            name = name.replace("_", " ").replace("-", " ")
            return name.title()

        # Fallback: method + path
        path_parts = [p for p in endpoint.path.split("/") if p and not p.startswith("{")]
        return f"{endpoint.method} {' '.join(path_parts)}".title()

    def _generate_tool_description(self, endpoint: OpenAPIEndpoint) -> str:
        """Genera una descrizione per il tool."""
        parts = []

        if endpoint.summary:
            parts.append(endpoint.summary)

        if endpoint.description and endpoint.description != endpoint.summary:
            parts.append(endpoint.description)

        if not parts:
            parts.append(f"{endpoint.method} {endpoint.path}")

        return " ".join(parts)

    def _extract_schema(self, endpoint: OpenAPIEndpoint) -> dict[str, Any]:
        """Estrae lo schema dei parametri per il tool."""
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        # Parametri path/query/header
        for param in endpoint.parameters:
            param_name = param.get("name", "unknown")
            param_schema = param.get("schema", {"type": "string"})
            param_desc = param.get("description", "")
            param_required = param.get("required", False)

            schema["properties"][param_name] = {
                **param_schema,
                "description": param_desc,
            }

            if param_required:
                schema["required"].append(param_name)

        # Request body
        if endpoint.request_body:
            content = endpoint.request_body.get("content", {})
            json_content = content.get("application/json", {})
            body_schema = json_content.get("schema", {})

            if body_schema:
                schema["properties"]["body"] = body_schema
                if endpoint.request_body.get("required", False):
                    schema["required"].append("body")

        return schema

    async def ingest_from_dict(
        self,
        tenant_id: str,
        spec: dict[str, Any],
        api_prefix: str | None = None,
    ) -> list[str]:
        """Ingesta una specifica OpenAPI da dizionario.

        Args:
            tenant_id: ID del tenant proprietario
            spec: Dizionario JSON OpenAPI
            api_prefix: Prefisso per i nomi dei tool (opzionale)

        Returns:
            Lista di tool_id creati
        """
        parsed = self.parse_openapi(spec)
        return await self._ingest_spec(tenant_id, parsed, api_prefix)

    async def ingest_from_file(
        self,
        tenant_id: str,
        file_path: str | Path,
        api_prefix: str | None = None,
    ) -> list[str]:
        """Ingesta una specifica OpenAPI da file.

        Args:
            tenant_id: ID del tenant proprietario
            file_path: Path al file OpenAPI (JSON o YAML)
            api_prefix: Prefisso per i nomi dei tool

        Returns:
            Lista di tool_id creati
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(path) as f:
            if path.suffix in [".yaml", ".yml"]:
                try:
                    import yaml

                    spec = yaml.safe_load(f)
                except ImportError:
                    raise ImportError("PyYAML required for YAML files: pip install pyyaml")
            else:
                spec = json.load(f)

        logger.info("openapi_file_loaded", path=str(path))

        return await self.ingest_from_dict(tenant_id, spec, api_prefix)

    async def ingest_from_url(
        self,
        tenant_id: str,
        url: str,
        api_prefix: str | None = None,
    ) -> list[str]:
        """Ingesta una specifica OpenAPI da URL.

        Args:
            tenant_id: ID del tenant proprietario
            url: URL della specifica OpenAPI
            api_prefix: Prefisso per i nomi dei tool

        Returns:
            Lista di tool_id creati
        """
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()

            if "yaml" in response.headers.get("content-type", ""):
                try:
                    import yaml

                    spec = yaml.safe_load(response.text)
                except ImportError:
                    raise ImportError("PyYAML required for YAML: pip install pyyaml")
            else:
                spec = response.json()

        logger.info("openapi_url_loaded", url=url)

        return await self.ingest_from_dict(tenant_id, spec, api_prefix)

    async def _ingest_spec(
        self,
        tenant_id: str,
        spec: OpenAPISpec,
        api_prefix: str | None = None,
    ) -> list[str]:
        """Ingesta una specifica parsata nel Procedural Memory.

        Per ogni endpoint:
        1. Crea un Tool nel Skill Graph (KuzuDB)
        2. Genera embedding della descrizione
        3. Opzionalmente crea Intent nodes basati sui tag

        Returns:
            Lista di tool_id creati
        """
        procedural = self.get_procedural()
        get_embedding_service()

        prefix = f"{api_prefix} " if api_prefix else ""
        tool_ids = []

        for endpoint in spec.endpoints:
            # Genera nome e descrizione
            name = f"{prefix}{self._generate_tool_name(endpoint)}"
            description = self._generate_tool_description(endpoint)

            # Costruisci endpoint URL
            endpoint_url = f"{spec.base_url or ''}{endpoint.path}"

            # Crea Tool
            tool = Tool(
                id=str(uuid4()),
                name=name,
                description=description,
                tenant_id=tenant_id,
                endpoint=endpoint_url,
                method=endpoint.method,
                api_schema=self._extract_schema(endpoint),
                status="ACTIVE",
                version=spec.version,
            )

            # Registra nel Skill Graph
            tool_id = procedural.register_tool(tool)
            tool_ids.append(tool_id)

            # Registra Intent basati sui tag
            if endpoint.tags:
                for tag in endpoint.tags:
                    intent_text = f"{tag.replace('_', ' ').replace('-', ' ').title()}"
                    procedural.register_intent(
                        tenant_id=tenant_id,
                        intent=intent_text,
                        tool_ids=[tool_id],
                        initial_weight=0.5,
                    )

            logger.debug(
                "tool_ingested",
                tool_id=tool_id,
                name=name,
                method=endpoint.method,
                path=endpoint.path,
            )

        logger.info(
            "openapi_ingestion_complete",
            tenant_id=tenant_id,
            api_title=spec.title,
            tools_created=len(tool_ids),
        )

        return tool_ids


# Factory
def create_openapi_ingester() -> OpenAPIIngester:
    """Crea un nuovo ingester OpenAPI."""
    return OpenAPIIngester()
