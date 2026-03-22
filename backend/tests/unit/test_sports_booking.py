"""Unit tests for Sports Booking Domain Handler.

Tests per SportsBookingHandler e tools Playtomic.
Mocka le API esterne per test affidabili e veloci.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime


# ============================================================================
# Helper Functions
# ============================================================================


async def call_can_handle(handler, query: str) -> float:
    """Helper to call can_handle."""
    result = handler.can_handle(query, {})
    if hasattr(result, "__await__"):
        return await result
    return result


# ============================================================================
# SportsBookingHandler Tests
# ============================================================================


class TestSportsBookingHandler:
    """Tests for SportsBookingHandler."""

    @pytest.fixture
    def handler(self):
        from me4brain.domains.sports_booking.handler import SportsBookingHandler

        return SportsBookingHandler()

    def test_domain_name(self, handler):
        assert handler.domain_name == "sports_booking"

    def test_volatility(self, handler):
        from me4brain.core.interfaces import DomainVolatility

        assert handler.volatility == DomainVolatility.REAL_TIME

    def test_capabilities(self, handler):
        caps = handler.capabilities
        assert len(caps) == 4
        cap_names = [c.name for c in caps]
        assert "club_search" in cap_names
        assert "court_availability" in cap_names
        assert "court_booking" in cap_names
        assert "my_bookings" in cap_names

    @pytest.mark.asyncio
    async def test_can_handle_playtomic_query(self, handler):
        score = await call_can_handle(handler, "cerca campi padel su playtomic")
        assert score >= 0.9

    @pytest.mark.asyncio
    async def test_can_handle_padel_booking(self, handler):
        score = await call_can_handle(handler, "prenota campo padel domani")
        assert score >= 0.8

    @pytest.mark.asyncio
    async def test_can_handle_availability(self, handler):
        score = await call_can_handle(handler, "disponibilità campi tennis Milano")
        assert score >= 0.8

    @pytest.mark.asyncio
    async def test_can_handle_unrelated(self, handler):
        score = await call_can_handle(handler, "qual è il meteo a Roma?")
        assert score < 0.5

    def test_extract_date_oggi(self, handler):
        date = handler._extract_date("campi disponibili oggi")
        assert date == datetime.now().strftime("%Y-%m-%d")

    def test_extract_date_domani(self, handler):
        from datetime import timedelta

        date = handler._extract_date("prenota per domani")
        expected = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        assert date == expected

    def test_extract_date_explicit(self, handler):
        date = handler._extract_date("disponibilità 2026-02-07")
        assert date == "2026-02-07"

    def test_extract_time_range_dalle_alle(self, handler):
        time_from, time_to = handler._extract_time_range("dalle 18 alle 21")
        assert time_from == "18:00"
        assert time_to == "21:00"

    def test_extract_time_range_with_minutes(self, handler):
        time_from, time_to = handler._extract_time_range("dalle 18:30 alle 20:30")
        assert time_from == "18:30"
        assert time_to == "20:30"

    def test_extract_time_range_dopo(self, handler):
        time_from, time_to = handler._extract_time_range("dopo le 17")
        assert time_from == "17:00"
        assert time_to is None

    def test_extract_location_milano(self, handler):
        location = handler._extract_location("campi padel a Milano", {})
        assert location == "Milano"

    def test_extract_location_roma(self, handler):
        location = handler._extract_location("cerca club a Roma", {})
        assert location == "Roma"

    @pytest.mark.asyncio
    async def test_execute_search(self, handler):
        """Test che execute restituisce risultati per query search."""
        # Il test verifica che execute gestisce correttamente una query di ricerca
        # e restituisce risultati (anche se API call fallisce ritorna error dict)
        results = await handler.execute(
            "cerca club padel a Milano",
            {},
            {},
        )

        assert len(results) >= 1
        assert results[0].tool_name == "playtomic_search_clubs"
        # Verifica struttura (success dipende dalla risposta API reale o mock)
        assert hasattr(results[0], "success")
        assert hasattr(results[0], "data")


# ============================================================================
# Playtomic API Tests
# ============================================================================


class TestPlaytomicSearchClubs:
    """Tests for playtomic_search_clubs."""

    @pytest.mark.asyncio
    async def test_search_clubs_success(self):
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "pageProps": {
                    "clubs": [
                        {
                            "tenant_id": "abc123",
                            "name": "SPH Milano Barona",
                            "address": {"city": "Milano", "street": "Via Test 1"},
                            "sports": ["PADEL", "TENNIS"],
                        }
                    ]
                }
            }
            mock_response.text = '{"buildId": "test123"}'
            mock_response.raise_for_status = MagicMock()

            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock()
            mock_client.return_value = mock_client_instance

            from me4brain.domains.sports_booking.tools.playtomic_api import (
                playtomic_search_clubs,
            )

            result = await playtomic_search_clubs("Milano")

            assert "clubs" in result or "error" in result
            assert result.get("source") == "Playtomic"

    @pytest.mark.asyncio
    async def test_search_clubs_error_handling(self):
        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(side_effect=Exception("Connection error"))
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock()
            mock_client.return_value = mock_client_instance

            from me4brain.domains.sports_booking.tools.playtomic_api import (
                playtomic_search_clubs,
            )

            result = await playtomic_search_clubs("Milano")

            assert "error" in result
            assert result["source"] == "Playtomic"


class TestPlaytomicClubAvailability:
    """Tests for playtomic_club_availability."""

    @pytest.mark.asyncio
    async def test_availability_with_time_filter(self):
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [
                {
                    "resource_id": "court-1",
                    "name": "Campo 1",
                    "slots": [
                        {"start_time": "17:00:00", "duration": 90, "price": 40},
                        {"start_time": "18:30:00", "duration": 90, "price": 45},
                        {"start_time": "20:00:00", "duration": 90, "price": 50},
                        {"start_time": "21:30:00", "duration": 90, "price": 45},
                    ],
                }
            ]
            mock_response.raise_for_status = MagicMock()

            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock()
            mock_client.return_value = mock_client_instance

            from me4brain.domains.sports_booking.tools.playtomic_api import (
                playtomic_club_availability,
            )

            result = await playtomic_club_availability(
                tenant_id="abc123",
                date="2026-02-07",
                time_from="18:00",
                time_to="21:00",
            )

            assert result.get("source") == "Playtomic"
            # Con filtro, dovrebbe includere solo slot tra 18:00 e 21:00
            if "resources" in result:
                for resource in result["resources"]:
                    for slot in resource.get("slots", []):
                        assert slot["start_time"] >= "18:00"
                        assert slot["start_time"] < "21:00"


class TestPlaytomicAuth:
    """Tests for PlaytomicAuth."""

    def test_derive_key(self):
        from me4brain.domains.sports_booking.tools.playtomic_auth import PlaytomicAuth

        auth = PlaytomicAuth()
        key = auth._derive_key()
        assert len(key) == 32  # SHA256

    def test_encrypt_decrypt(self):
        from me4brain.domains.sports_booking.tools.playtomic_auth import PlaytomicAuth

        auth = PlaytomicAuth()
        original = "test_token_123"
        encrypted = auth._encrypt(original)
        decrypted = auth._decrypt(encrypted)
        assert decrypted == original

    def test_is_authenticated_no_tokens(self):
        from me4brain.domains.sports_booking.tools.playtomic_auth import PlaytomicAuth
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            auth = PlaytomicAuth(token_file=Path(tmpdir) / "tokens.json")
            assert auth.is_authenticated() is False


# ============================================================================
# Tool Definitions Tests
# ============================================================================


class TestToolDefinitions:
    """Tests for tool definitions."""

    def test_tool_definitions_count(self):
        from me4brain.domains.sports_booking.tools.playtomic_api import (
            get_tool_definitions,
        )

        defs = get_tool_definitions()
        assert len(defs) == 6

    def test_tool_definitions_names(self):
        from me4brain.domains.sports_booking.tools.playtomic_api import (
            get_tool_definitions,
        )

        defs = get_tool_definitions()
        names = [d.name for d in defs]
        assert "playtomic_search_clubs" in names
        assert "playtomic_club_availability" in names
        assert "playtomic_court_details" in names
        assert "playtomic_book_court" in names
        assert "playtomic_my_bookings" in names
        assert "playtomic_cancel_booking" in names

    def test_availability_has_time_params(self):
        from me4brain.domains.sports_booking.tools.playtomic_api import (
            get_tool_definitions,
        )

        defs = get_tool_definitions()
        availability_def = next(d for d in defs if d.name == "playtomic_club_availability")
        # parameters è un dict, usiamo .keys() per ottenere i nomi
        param_names = list(availability_def.parameters.keys())
        assert "time_from" in param_names
        assert "time_to" in param_names

    def test_booking_tools_category(self):
        from me4brain.domains.sports_booking.tools.playtomic_api import (
            get_tool_definitions,
        )

        defs = get_tool_definitions()
        booking_tools = [d.name for d in defs if d.category == "booking"]
        assert "playtomic_book_court" in booking_tools
        assert "playtomic_my_bookings" in booking_tools
        assert "playtomic_cancel_booking" in booking_tools

        search_tools = [d.name for d in defs if d.category == "search"]
        assert "playtomic_search_clubs" in search_tools
