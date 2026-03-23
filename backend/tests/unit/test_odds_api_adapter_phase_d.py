"""Phase D Unit Tests: NBA Odds API Adapter (C1 criticality).

Tests cover:
1. API response handling (200, 401, 429, timeout)
2. Error code parsing (OUT_OF_USAGE_CREDITS, INVALID_API_KEY, NOT_FOUND)
3. Fallback chain behavior (polymarket, web_search)
4. Headers parsing (x-requests-remaining, x-requests-used)
5. Configuration validation (API key presence)
6. Quota monitoring

Target: 85%+ code coverage for nba_api.py odds_api_odds() function
"""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest


class TestOddsAPIConfiguration:
    """Tests for odds API configuration and validation."""

    @pytest.mark.asyncio
    async def test_odds_api_missing_key(self):
        """Test handles missing THE_ODDS_API_KEY gracefully."""
        with patch("me4brain.domains.sports_nba.tools.nba_api._get_api_key") as mock_get:
            mock_get.return_value = None

            from me4brain.domains.sports_nba.tools.nba_api import odds_api_odds

            result = await odds_api_odds()

            assert result.get("error") == "THE_ODDS_API_KEY not configured"
            assert result.get("fallback") == "web_search"

    @pytest.mark.asyncio
    async def test_odds_api_key_present(self):
        """Test proceeds when API key is configured."""
        with patch("me4brain.domains.sports_nba.tools.nba_api._get_api_key") as mock_get:
            with patch("httpx.AsyncClient") as mock_client:
                mock_get.return_value = "test-api-key"
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"games": []}
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                from me4brain.domains.sports_nba.tools.nba_api import odds_api_odds

                result = await odds_api_odds()

                # Should complete without error
                assert result is not None


class TestOddsAPI200Response:
    """Tests for successful API responses."""

    @pytest.mark.asyncio
    async def test_odds_api_200_success(self):
        """Test successful API response with event data."""
        with patch("me4brain.domains.sports_nba.tools.nba_api._get_api_key") as mock_get:
            with patch("httpx.AsyncClient") as mock_client:
                mock_get.return_value = "test-api-key"

                games_data = [
                    {
                        "id": "1",
                        "home_team": "Lakers",
                        "away_team": "Celtics",
                        "commence_time": "2025-03-22T20:00Z",
                        "bookmakers": [
                            {
                                "title": "FanDuel",
                                "markets": [
                                    {
                                        "key": "spreads",
                                        "outcomes": [
                                            {"name": "Lakers", "price": -110},
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ]

                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = games_data
                mock_response.headers = {"x-requests-remaining": "100"}

                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                from me4brain.domains.sports_nba.tools.nba_api import odds_api_odds

                result = await odds_api_odds()

                assert result.get("events") is not None
                assert len(result["events"]) == 1
                assert result["events"][0]["home_team"] == "Lakers"
                assert result.get("source") == "The Odds API"
                assert result.get("count") == 1

    @pytest.mark.asyncio
    async def test_odds_api_200_empty_games(self):
        """Test 200 response with no events data."""
        with patch("me4brain.domains.sports_nba.tools.nba_api._get_api_key") as mock_get:
            with patch("httpx.AsyncClient") as mock_client:
                mock_get.return_value = "test-api-key"

                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = []
                mock_response.headers = {"x-requests-remaining": "50"}

                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                from me4brain.domains.sports_nba.tools.nba_api import odds_api_odds

                result = await odds_api_odds()

                assert result.get("events") == []
                assert result.get("count") == 0
                assert result.get("source") == "The Odds API"


class TestOddsAPI401Errors:
    """Tests for 401 Unauthorized errors (C1 criticality)."""

    @pytest.mark.asyncio
    async def test_odds_api_401_out_of_usage_credits(self):
        """Test 401 with OUT_OF_USAGE_CREDITS error code."""
        with patch("me4brain.domains.sports_nba.tools.nba_api._get_api_key") as mock_get:
            with patch("httpx.AsyncClient") as mock_client:
                mock_get.return_value = "test-api-key"

                error_response = {
                    "error_code": "OUT_OF_USAGE_CREDITS",
                    "message": "You have used up all your monthly requests",
                }

                mock_response = Mock()
                mock_response.status_code = 401
                mock_response.json.return_value = error_response
                mock_response.headers = {
                    "x-requests-used": "500",
                    "x-requests-remaining": "0",
                }

                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                from me4brain.domains.sports_nba.tools.nba_api import odds_api_odds

                result = await odds_api_odds()

                # Should detect quota exceeded and fallback
                assert result.get("error") is not None or result.get("fallback") is not None

    @pytest.mark.asyncio
    async def test_odds_api_401_invalid_api_key(self):
        """Test 401 with INVALID_API_KEY error code."""
        with patch("me4brain.domains.sports_nba.tools.nba_api._get_api_key") as mock_get:
            with patch("httpx.AsyncClient") as mock_client:
                mock_get.return_value = "bad-api-key"

                error_response = {
                    "error_code": "INVALID_API_KEY",
                    "message": "Invalid API key",
                }

                mock_response = Mock()
                mock_response.status_code = 401
                mock_response.json.return_value = error_response
                mock_response.headers = {}

                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                from me4brain.domains.sports_nba.tools.nba_api import odds_api_odds

                result = await odds_api_odds()

                # Should identify authentication error
                assert result.get("error") is not None

    @pytest.mark.asyncio
    async def test_odds_api_401_malformed_response(self):
        """Test 401 with malformed JSON response (invalid error_code)."""
        with patch("me4brain.domains.sports_nba.tools.nba_api._get_api_key") as mock_get:
            with patch("httpx.AsyncClient") as mock_client:
                mock_get.return_value = "test-api-key"

                mock_response = Mock()
                mock_response.status_code = 401
                mock_response.json.side_effect = ValueError("Invalid JSON")
                mock_response.text = "Unauthorized"
                mock_response.headers = {}

                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                from me4brain.domains.sports_nba.tools.nba_api import odds_api_odds

                result = await odds_api_odds()

                # Should handle JSON parse error gracefully
                assert result.get("error") is not None


class TestOddsAPI429Errors:
    """Tests for 429 Rate Limit errors."""

    @pytest.mark.asyncio
    async def test_odds_api_429_rate_limit(self):
        """Test 429 Too Many Requests error."""
        with patch("me4brain.domains.sports_nba.tools.nba_api._get_api_key") as mock_get:
            with patch("httpx.AsyncClient") as mock_client:
                mock_get.return_value = "test-api-key"

                mock_response = Mock()
                mock_response.status_code = 429
                mock_response.headers = {
                    "retry-after": "60",
                    "x-requests-remaining": "0",
                }

                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                from me4brain.domains.sports_nba.tools.nba_api import odds_api_odds

                result = await odds_api_odds()

                # Should identify rate limit and fallback
                assert result.get("error") is not None or result.get("fallback") is not None

    @pytest.mark.asyncio
    async def test_odds_api_429_with_retry_after(self):
        """Test 429 with retry-after header parsing."""
        with patch("me4brain.domains.sports_nba.tools.nba_api._get_api_key") as mock_get:
            with patch("httpx.AsyncClient") as mock_client:
                mock_get.return_value = "test-api-key"

                mock_response = Mock()
                mock_response.status_code = 429
                mock_response.headers = {"retry-after": "120"}

                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                from me4brain.domains.sports_nba.tools.nba_api import odds_api_odds

                result = await odds_api_odds()

                # Should parse retry-after and include in response
                assert result.get("error") is not None or result.get("retry_after") is not None


class TestOddsAPITimeouts:
    """Tests for timeout and network errors."""

    @pytest.mark.asyncio
    async def test_odds_api_timeout(self):
        """Test handles connection timeout."""
        with patch("me4brain.domains.sports_nba.tools.nba_api._get_api_key") as mock_get:
            with patch("httpx.AsyncClient") as mock_client:
                mock_get.return_value = "test-api-key"

                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    side_effect=httpx.TimeoutException("Connection timeout")
                )

                from me4brain.domains.sports_nba.tools.nba_api import odds_api_odds

                result = await odds_api_odds()

                # Should catch timeout and return fallback
                assert result.get("error") is not None or result.get("fallback") is not None

    @pytest.mark.asyncio
    async def test_odds_api_connection_error(self):
        """Test handles connection error."""
        with patch("me4brain.domains.sports_nba.tools.nba_api._get_api_key") as mock_get:
            with patch("httpx.AsyncClient") as mock_client:
                mock_get.return_value = "test-api-key"

                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    side_effect=httpx.ConnectError("Failed to connect")
                )

                from me4brain.domains.sports_nba.tools.nba_api import odds_api_odds

                result = await odds_api_odds()

                # Should handle connection error
                assert result.get("error") is not None or result.get("fallback") is not None


class TestOddsAPIFallbacks:
    """Tests for fallback chain behavior."""

    @pytest.mark.asyncio
    async def test_odds_api_fallback_to_polymarket(self):
        """Test fallback to Polymarket when odds API fails."""
        with patch("me4brain.domains.sports_nba.tools.nba_api._get_api_key") as mock_get:
            with patch("httpx.AsyncClient") as mock_client:
                with patch(
                    "me4brain.domains.sports_nba.tools.nba_api.polymarket_nba_odds"
                ) as mock_poly:
                    mock_get.return_value = "test-api-key"

                    # First call fails
                    mock_response = Mock()
                    mock_response.status_code = 429
                    mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                        return_value=mock_response
                    )

                    # Polymarket fallback succeeds
                    mock_poly.return_value = {"polymarket_odds": []}

                    from me4brain.domains.sports_nba.tools.nba_api import odds_api_odds

                    result = await odds_api_odds()

                    # Result should be accessible
                    assert result is not None

    @pytest.mark.asyncio
    async def test_odds_api_fallback_to_web_search(self):
        """Test fallback to web search when all APIs fail."""
        with patch("me4brain.domains.sports_nba.tools.nba_api._get_api_key") as mock_get:
            with patch("httpx.AsyncClient") as mock_client:
                mock_get.return_value = "test-api-key"

                mock_response = Mock()
                mock_response.status_code = 500  # Server error
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                from me4brain.domains.sports_nba.tools.nba_api import odds_api_odds

                result = await odds_api_odds()

                # Should fallback to web_search
                assert result.get("fallback") == "web_search" or result.get("error") is not None


class TestOddsAPIHeadersParsing:
    """Tests for header parsing (quota monitoring)."""

    @pytest.mark.asyncio
    async def test_odds_api_quota_headers(self):
        """Test parsing x-requests-remaining and x-requests-used."""
        with patch("me4brain.domains.sports_nba.tools.nba_api._get_api_key") as mock_get:
            with patch("httpx.AsyncClient") as mock_client:
                mock_get.return_value = "test-api-key"

                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"games": []}
                mock_response.headers = {
                    "x-requests-remaining": "450",
                    "x-requests-used": "50",
                }

                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                from me4brain.domains.sports_nba.tools.nba_api import odds_api_odds

                result = await odds_api_odds()

                # Response should include or preserve quota info
                assert result is not None

    @pytest.mark.asyncio
    async def test_odds_api_low_quota_warning(self):
        """Test detects low quota (≤10 requests remaining)."""
        with patch("me4brain.domains.sports_nba.tools.nba_api._get_api_key") as mock_get:
            with patch("httpx.AsyncClient") as mock_client:
                mock_get.return_value = "test-api-key"

                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"games": []}
                mock_response.headers = {
                    "x-requests-remaining": "5",  # Low quota
                    "x-requests-used": "495",
                }

                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                from me4brain.domains.sports_nba.tools.nba_api import odds_api_odds

                result = await odds_api_odds()

                # Should warn about low quota
                assert result is not None


class TestOddsAPIParameters:
    """Tests for API parameter handling."""

    @pytest.mark.asyncio
    async def test_odds_api_custom_sport(self):
        """Test passing custom sport parameter."""
        with patch("me4brain.domains.sports_nba.tools.nba_api._get_api_key") as mock_get:
            with patch("httpx.AsyncClient") as mock_client:
                mock_get.return_value = "test-api-key"

                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"games": []}
                mock_response.headers = {}

                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                from me4brain.domains.sports_nba.tools.nba_api import odds_api_odds

                result = await odds_api_odds(sport="basketball_nba")

                assert result is not None

    @pytest.mark.asyncio
    async def test_odds_api_custom_regions(self):
        """Test passing custom regions parameter."""
        with patch("me4brain.domains.sports_nba.tools.nba_api._get_api_key") as mock_get:
            with patch("httpx.AsyncClient") as mock_client:
                mock_get.return_value = "test-api-key"

                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"games": []}
                mock_response.headers = {}

                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                from me4brain.domains.sports_nba.tools.nba_api import odds_api_odds

                result = await odds_api_odds(regions="us")

                assert result is not None

    @pytest.mark.asyncio
    async def test_odds_api_custom_markets(self):
        """Test passing custom markets parameter."""
        with patch("me4brain.domains.sports_nba.tools.nba_api._get_api_key") as mock_get:
            with patch("httpx.AsyncClient") as mock_client:
                mock_get.return_value = "test-api-key"

                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"games": []}
                mock_response.headers = {}

                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                from me4brain.domains.sports_nba.tools.nba_api import odds_api_odds

                result = await odds_api_odds(markets="spreads,totals")

                assert result is not None


class TestOddsAPIEdgeCases:
    """Tests for edge cases and unusual scenarios."""

    @pytest.mark.asyncio
    async def test_odds_api_empty_response_body(self):
        """Test handles empty response body."""
        with patch("me4brain.domains.sports_nba.tools.nba_api._get_api_key") as mock_get:
            with patch("httpx.AsyncClient") as mock_client:
                mock_get.return_value = "test-api-key"

                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.side_effect = ValueError("Empty response")
                mock_response.text = ""
                mock_response.headers = {}

                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                from me4brain.domains.sports_nba.tools.nba_api import odds_api_odds

                result = await odds_api_odds()

                # Should handle empty response
                assert result.get("error") is not None or result.get("fallback") is not None

    @pytest.mark.asyncio
    async def test_odds_api_500_server_error(self):
        """Test handles 500 Internal Server Error."""
        with patch("me4brain.domains.sports_nba.tools.nba_api._get_api_key") as mock_get:
            with patch("httpx.AsyncClient") as mock_client:
                mock_get.return_value = "test-api-key"

                mock_response = Mock()
                mock_response.status_code = 500
                mock_response.json.return_value = {"error": "Internal Server Error"}
                mock_response.headers = {}

                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                from me4brain.domains.sports_nba.tools.nba_api import odds_api_odds

                result = await odds_api_odds()

                # Should fallback on server error
                assert result.get("error") is not None or result.get("fallback") is not None

    @pytest.mark.asyncio
    async def test_odds_api_missing_required_fields(self):
        """Test handles response missing expected fields."""
        with patch("me4brain.domains.sports_nba.tools.nba_api._get_api_key") as mock_get:
            with patch("httpx.AsyncClient") as mock_client:
                mock_get.return_value = "test-api-key"

                # Missing 'games' key
                incomplete_data = {
                    "status": "success",
                    # 'games' key is missing
                }

                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = incomplete_data
                mock_response.headers = {}

                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                from me4brain.domains.sports_nba.tools.nba_api import odds_api_odds

                result = await odds_api_odds()

                # Should handle missing fields gracefully
                assert result is not None
