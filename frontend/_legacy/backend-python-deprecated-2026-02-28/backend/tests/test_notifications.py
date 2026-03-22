"""Tests for NotificationDispatcher.

Tests cover:
- WebSocket push via Gateway
- Telegram notification
- Slack notification
- Error handling
- Multi-channel dispatch
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from backend.proactive.notifications import NotificationDispatcher, format_stock_alert
from backend.proactive.monitors import NotifyChannel


@pytest.fixture
def dispatcher():
    """Create dispatcher with test configuration."""
    return NotificationDispatcher(
        telegram_bot_token="test-token-123",
        slack_webhook_url="https://hooks.slack.com/test",
        gateway_url="http://localhost:3000",
    )


@pytest.fixture
def dispatcher_no_config():
    """Create dispatcher without external services configured."""
    return NotificationDispatcher()


class TestNotificationDispatcher:
    """Test suite for NotificationDispatcher."""

    @pytest.mark.asyncio
    async def test_dispatch_websocket_success(self, dispatcher):
        """Test successful WebSocket notification via Gateway."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True, "sent": 1}

        with patch.object(dispatcher, "_get_client") as mock_client:
            client = AsyncMock()
            client.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = client

            results = await dispatcher.dispatch(
                user_id="test_user",
                channels=[NotifyChannel.WEB],
                title="Test Alert",
                message="This is a test",
            )

            assert results["web"] is True

    @pytest.mark.asyncio
    async def test_dispatch_websocket_no_connections(self, dispatcher):
        """Test WebSocket when no users are connected."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True, "sent": 0}

        with patch.object(dispatcher, "_get_client") as mock_client:
            client = AsyncMock()
            client.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = client

            results = await dispatcher.dispatch(
                user_id="offline_user",
                channels=[NotifyChannel.WEB],
                title="Test",
                message="Test",
            )

            # sent = 0, so should return False
            assert results["web"] is False

    @pytest.mark.asyncio
    async def test_dispatch_websocket_gateway_unavailable(self, dispatcher):
        """Test WebSocket when Gateway is unavailable."""
        with patch.object(dispatcher, "_get_client") as mock_client:
            client = AsyncMock()
            client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client.return_value = client

            results = await dispatcher.dispatch(
                user_id="test_user",
                channels=[NotifyChannel.WEB],
                title="Test",
                message="Test",
            )

            assert results["web"] is False

    @pytest.mark.asyncio
    async def test_dispatch_telegram_success(self, dispatcher):
        """Test successful Telegram notification."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(dispatcher, "_get_client") as mock_client:
            client = AsyncMock()
            client.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = client

            with patch.object(dispatcher, "_get_telegram_chat_id", return_value="123456"):
                results = await dispatcher.dispatch(
                    user_id="test_user",
                    channels=[NotifyChannel.TELEGRAM],
                    title="Stock Alert",
                    message="AAPL is below target",
                )

                assert results["telegram"] is True

                # Verify Telegram API was called
                client.post.assert_called()
                call_args = client.post.call_args
                assert "api.telegram.org" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_dispatch_telegram_no_chat_id(self, dispatcher):
        """Test Telegram when user has no chat_id mapping."""
        with patch.object(dispatcher, "_get_telegram_chat_id", return_value=None):
            results = await dispatcher.dispatch(
                user_id="unmapped_user",
                channels=[NotifyChannel.TELEGRAM],
                title="Test",
                message="Test",
            )

            assert results["telegram"] is False

    @pytest.mark.asyncio
    async def test_dispatch_telegram_no_token(self, dispatcher_no_config):
        """Test Telegram when bot token is not configured."""
        results = await dispatcher_no_config.dispatch(
            user_id="test_user",
            channels=[NotifyChannel.TELEGRAM],
            title="Test",
            message="Test",
        )

        assert results["telegram"] is False

    @pytest.mark.asyncio
    async def test_dispatch_slack_success(self, dispatcher):
        """Test successful Slack notification."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(dispatcher, "_get_client") as mock_client:
            client = AsyncMock()
            client.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = client

            results = await dispatcher.dispatch(
                user_id="test_user",
                channels=[NotifyChannel.SLACK],
                title="Team Alert",
                message="Important notification",
            )

            assert results["slack"] is True

            # Verify Slack webhook was called
            client.post.assert_called()
            call_args = client.post.call_args
            assert "hooks.slack.com" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_dispatch_slack_no_webhook(self, dispatcher_no_config):
        """Test Slack when webhook is not configured."""
        results = await dispatcher_no_config.dispatch(
            user_id="test_user",
            channels=[NotifyChannel.SLACK],
            title="Test",
            message="Test",
        )

        assert results["slack"] is False

    @pytest.mark.asyncio
    async def test_dispatch_email_not_implemented(self, dispatcher):
        """Test that email returns False (not implemented)."""
        results = await dispatcher.dispatch(
            user_id="test_user",
            channels=[NotifyChannel.EMAIL],
            title="Test",
            message="Test",
        )

        assert results["email"] is False

    @pytest.mark.asyncio
    async def test_dispatch_whatsapp_not_implemented(self, dispatcher):
        """Test that WhatsApp returns False (not implemented)."""
        results = await dispatcher.dispatch(
            user_id="test_user",
            channels=[NotifyChannel.WHATSAPP],
            title="Test",
            message="Test",
        )

        assert results["whatsapp"] is False

    @pytest.mark.asyncio
    async def test_dispatch_multi_channel(self, dispatcher):
        """Test dispatching to multiple channels."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True, "sent": 1}

        with patch.object(dispatcher, "_get_client") as mock_client:
            client = AsyncMock()
            client.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = client

            with patch.object(dispatcher, "_get_telegram_chat_id", return_value="123456"):
                results = await dispatcher.dispatch(
                    user_id="test_user",
                    channels=[NotifyChannel.WEB, NotifyChannel.TELEGRAM, NotifyChannel.SLACK],
                    title="Multi Alert",
                    message="Sent to all channels",
                )

                assert results["web"] is True
                assert results["telegram"] is True
                assert results["slack"] is True


class TestFormatStockAlert:
    """Test stock alert formatting."""

    def test_format_buy_alert(self):
        """Test formatting BUY alert."""
        title, message = format_stock_alert(
            ticker="AAPL",
            recommendation="BUY",
            confidence=85,
            reasoning="Strong technical setup with RSI oversold",
            key_factors=["RSI < 30", "Volume surge", "Support level held"],
            suggested_action="Consider buying at current levels",
        )

        assert "AAPL" in title
        assert "📈" in title  # Buy emoji
        assert "BUY" in message
        assert "85%" in message
        assert "RSI < 30" in message
        assert "Consider buying" in message

    def test_format_sell_alert(self):
        """Test formatting SELL alert."""
        title, message = format_stock_alert(
            ticker="NVDA",
            recommendation="SELL",
            confidence=70,
            reasoning="Overbought conditions",
            key_factors=["RSI > 70", "MACD crossover"],
        )

        assert "NVDA" in title
        assert "📉" in title  # Sell emoji
        assert "SELL" in message
        assert "70%" in message

    def test_format_hold_alert(self):
        """Test formatting HOLD alert."""
        title, message = format_stock_alert(
            ticker="GOOGL",
            recommendation="HOLD",
            confidence=50,
            reasoning="Mixed signals",
            key_factors=["Neutral momentum"],
        )

        assert "GOOGL" in title
        assert "➖" in title  # Hold emoji
        assert "HOLD" in message


class TestDispatcherCleanup:
    """Test resource cleanup."""

    @pytest.mark.asyncio
    async def test_close_releases_resources(self, dispatcher):
        """Test that close() releases HTTP client."""
        # Force client creation
        client = await dispatcher._get_client()

        # Close dispatcher
        await dispatcher.close()

        # Client should be None
        assert dispatcher._http_client is None
