"""Test OpenAPI Ingester."""

import json
import pytest

from unittest.mock import AsyncMock, MagicMock, patch
from me4brain.retrieval.openapi_ingester import (
    OpenAPIEndpoint,
    OpenAPIIngester,
    OpenAPISpec,
)


class TestOpenAPIIngester:
    """Test suite per OpenAPI Ingester."""

    @pytest.fixture
    def sample_openapi_spec(self) -> dict:
        """Specifica OpenAPI di esempio."""
        return {
            "openapi": "3.0.0",
            "info": {
                "title": "Pet Store API",
                "version": "1.0.0",
                "description": "A sample pet store API",
            },
            "servers": [{"url": "https://api.petstore.io/v1"}],
            "paths": {
                "/pets": {
                    "get": {
                        "operationId": "listPets",
                        "summary": "List all pets",
                        "description": "Returns all pets in the store",
                        "tags": ["pets"],
                        "parameters": [
                            {
                                "name": "limit",
                                "in": "query",
                                "description": "Maximum items to return",
                                "required": False,
                                "schema": {"type": "integer"},
                            }
                        ],
                        "responses": {
                            "200": {"description": "A list of pets"},
                        },
                    },
                    "post": {
                        "operationId": "createPet",
                        "summary": "Create a pet",
                        "tags": ["pets"],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "species": {"type": "string"},
                                        },
                                    }
                                }
                            },
                        },
                        "responses": {
                            "201": {"description": "Pet created"},
                        },
                    },
                },
                "/pets/{petId}": {
                    "get": {
                        "operationId": "getPetById",
                        "summary": "Get pet by ID",
                        "tags": ["pets"],
                        "parameters": [
                            {
                                "name": "petId",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                            }
                        ],
                        "responses": {
                            "200": {"description": "A pet"},
                        },
                    },
                },
            },
        }

    @pytest.fixture
    def ingester(self) -> OpenAPIIngester:
        """Crea un ingester per i test."""
        return OpenAPIIngester()

    def test_parse_openapi_basic_info(
        self,
        ingester: OpenAPIIngester,
        sample_openapi_spec: dict,
    ) -> None:
        """Test parsing info generali."""
        spec = ingester.parse_openapi(sample_openapi_spec)

        assert spec.title == "Pet Store API"
        assert spec.version == "1.0.0"
        assert spec.description == "A sample pet store API"
        assert spec.base_url == "https://api.petstore.io/v1"

    def test_parse_openapi_endpoints_count(
        self,
        ingester: OpenAPIIngester,
        sample_openapi_spec: dict,
    ) -> None:
        """Test conteggio endpoints."""
        spec = ingester.parse_openapi(sample_openapi_spec)

        # GET /pets, POST /pets, GET /pets/{petId}
        assert len(spec.endpoints) == 3

    def test_parse_openapi_endpoint_details(
        self,
        ingester: OpenAPIIngester,
        sample_openapi_spec: dict,
    ) -> None:
        """Test dettagli endpoint."""
        spec = ingester.parse_openapi(sample_openapi_spec)

        # Trova GET /pets
        list_pets = next(
            (e for e in spec.endpoints if e.operation_id == "listPets"),
            None,
        )

        assert list_pets is not None
        assert list_pets.path == "/pets"
        assert list_pets.method == "GET"
        assert list_pets.summary == "List all pets"
        assert "pets" in list_pets.tags

    def test_generate_tool_name_from_operation_id(
        self,
        ingester: OpenAPIIngester,
    ) -> None:
        """Test generazione nome tool da operationId."""
        endpoint = OpenAPIEndpoint(
            path="/pets",
            method="GET",
            operation_id="listAllPets",
        )

        name = ingester._generate_tool_name(endpoint)
        assert "List" in name
        assert "All" in name
        assert "Pets" in name

    def test_generate_tool_name_fallback(
        self,
        ingester: OpenAPIIngester,
    ) -> None:
        """Test fallback se nessun operationId."""
        endpoint = OpenAPIEndpoint(
            path="/pets/{id}/photos",
            method="GET",
        )

        name = ingester._generate_tool_name(endpoint)
        assert "GET" in name.upper()
        assert "Pets" in name or "pets" in name.lower()

    def test_extract_schema_parameters(
        self,
        ingester: OpenAPIIngester,
    ) -> None:
        """Test estrazione schema dai parametri."""
        endpoint = OpenAPIEndpoint(
            path="/pets",
            method="GET",
            parameters=[
                {
                    "name": "limit",
                    "in": "query",
                    "required": True,
                    "schema": {"type": "integer"},
                    "description": "Max items",
                },
                {
                    "name": "offset",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "integer"},
                },
            ],
        )

        schema = ingester._extract_schema(endpoint)

        assert "limit" in schema["properties"]
        assert "offset" in schema["properties"]
        assert "limit" in schema["required"]
        assert "offset" not in schema["required"]

    def test_extract_schema_request_body(
        self,
        ingester: OpenAPIIngester,
    ) -> None:
        """Test estrazione schema dal request body."""
        endpoint = OpenAPIEndpoint(
            path="/pets",
            method="POST",
            request_body={
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}},
                        }
                    }
                },
            },
        )

        schema = ingester._extract_schema(endpoint)

        assert "body" in schema["properties"]
        assert "body" in schema["required"]

    @pytest.mark.asyncio
    async def test_ingest_from_dict_mocked(
        self,
        ingester: OpenAPIIngester,
        sample_openapi_spec: dict,
    ) -> None:
        """Test ingestion completa con mock dei servizi."""
        with (
            patch("me4brain.retrieval.openapi_ingester.get_procedural_memory") as mock_proc_getter,
            patch("me4brain.retrieval.openapi_ingester.get_embedding_service") as mock_emb_getter,
        ):
            proc = MagicMock()
            mock_proc_getter.return_value = proc
            mock_emb_getter.return_value = MagicMock()

            proc.register_tool.return_value = "tool_123"

            tool_ids = await ingester.ingest_from_dict(
                tenant_id="test_tenant", spec=sample_openapi_spec, api_prefix="PET"
            )

            assert len(tool_ids) == 3
            assert tool_ids[0] == "tool_123"
            assert proc.register_tool.call_count == 3
            # Verifica che i tag abbiano generato intent
            assert proc.register_intent.call_count >= 1

    @pytest.mark.asyncio
    async def test_ingest_from_file_json(self, ingester, tmp_path):
        """Test caricamento da file JSON."""
        file_path = tmp_path / "spec.json"
        spec = {"openapi": "3.0.0", "info": {"title": "T"}, "paths": {}}
        file_path.write_text(json.dumps(spec))

        with patch.object(ingester, "ingest_from_dict", AsyncMock()) as mock_ingest:
            await ingester.ingest_from_file("t1", file_path)
            mock_ingest.assert_called_once()
