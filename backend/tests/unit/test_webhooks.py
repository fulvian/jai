"""Unit tests for Webhooks module (M6)."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from me4brain.core.webhooks.dispatcher import WebhookDispatcher
from me4brain.core.webhooks.receiver import WebhookReceiver
from me4brain.core.webhooks.types import (
    IncomingWebhookPayload,
    RetryPolicy,
    WebhookConfig,
    WebhookDelivery,
    WebhookEvent,
    WebhookEventType,
    WebhookResponse,
)

# --- Types Tests ---


class TestWebhookTypes:
    """Test per modelli Pydantic webhooks."""

    def test_webhook_event_type_enum(self):
        """Test enum valori corretti."""
        assert WebhookEventType.JOB_COMPLETED.value == "job.completed"
        assert WebhookEventType.AGENT_HANDOFF.value == "agent.handoff"
        assert WebhookEventType.EXTERNAL_TRIGGER.value == "external.trigger"

    def test_retry_policy_defaults(self):
        """Test valori default RetryPolicy."""
        policy = RetryPolicy()
        assert policy.max_attempts == 3
        assert policy.backoff_seconds == [1, 5, 15]
        assert policy.timeout_seconds == 30

    def test_webhook_config_creation(self):
        """Test creazione WebhookConfig."""
        config = WebhookConfig(
            id="test-123",
            name="Test Webhook",
            url="https://example.com/webhook",
            events=["job.completed", "job.failed"],
            secret="supersecret",
        )
        assert config.id == "test-123"
        assert config.enabled is True
        assert config.trigger_count == 0
        assert len(config.events) == 2

    def test_webhook_event_creation(self):
        """Test creazione WebhookEvent."""
        event = WebhookEvent(
            id="evt-123",
            type="job.completed",
            source="scheduler",
            payload={"job_id": "job-456"},
        )
        assert event.id == "evt-123"
        assert event.signature is None
        assert event.payload["job_id"] == "job-456"

    def test_webhook_delivery_creation(self):
        """Test creazione WebhookDelivery."""
        delivery = WebhookDelivery(
            id="del-123",
            config_id="cfg-123",
            event_id="evt-123",
            attempted_at=datetime.now(),
            status="pending",
        )
        assert delivery.attempt == 1
        assert delivery.status == "pending"

    def test_webhook_response_from_config(self):
        """Test conversione WebhookResponse da config."""
        config = WebhookConfig(
            id="test-123",
            name="Test",
            url="https://example.com",
            events=["job.completed"],
            secret="secret",
            trigger_count=10,
            success_count=9,
        )
        response = WebhookResponse.from_config(config)
        assert response.id == "test-123"
        assert response.success_rate == 0.9


# --- Receiver Tests ---


class TestWebhookReceiver:
    """Test per WebhookReceiver."""

    def test_verify_signature_valid(self):
        """Test verifica signature valida."""
        receiver = WebhookReceiver(secret="mysecret")
        payload = b'{"test": "data"}'

        # Genera signature corretta
        expected = hmac.new(b"mysecret", payload, hashlib.sha256).hexdigest()

        assert receiver.verify_signature(payload, expected) is True

    def test_verify_signature_with_prefix(self):
        """Test verifica signature con prefisso sha256=."""
        receiver = WebhookReceiver(secret="mysecret")
        payload = b'{"test": "data"}'

        sig = hmac.new(b"mysecret", payload, hashlib.sha256).hexdigest()
        full_sig = f"sha256={sig}"

        assert receiver.verify_signature(payload, full_sig) is True

    def test_verify_signature_invalid(self):
        """Test verifica signature invalida."""
        receiver = WebhookReceiver(secret="mysecret")
        payload = b'{"test": "data"}'

        assert receiver.verify_signature(payload, "invalid") is False

    def test_verify_signature_no_secret_dev_mode(self):
        """Test dev mode senza secret."""
        receiver = WebhookReceiver()  # No secret
        payload = b'{"test": "data"}'

        # In dev mode, skip validation
        assert receiver.verify_signature(payload, "anything") is True

    def test_generate_signature(self):
        """Test generazione signature."""
        receiver = WebhookReceiver(secret="mysecret")
        payload = b'{"test": "data"}'

        sig = receiver.generate_signature(payload)
        assert sig.startswith("sha256=")
        assert len(sig) == 7 + 64  # "sha256=" + 64 hex chars

    @pytest.mark.asyncio
    async def test_receive_creates_event(self):
        """Test ricezione crea evento."""
        receiver = WebhookReceiver()

        payload = IncomingWebhookPayload(
            event_type="external.trigger",
            data={"key": "value"},
        )

        event = await receiver.receive(payload)

        assert event.type == "external.trigger"
        assert event.source == "external"
        assert event.payload == {"key": "value"}

    @pytest.mark.asyncio
    async def test_receive_with_signature_validation(self):
        """Test ricezione con validazione signature."""
        receiver = WebhookReceiver(secret="testsecret")

        raw_body = b'{"event_type":"test","data":{}}'
        sig = receiver.generate_signature(raw_body)

        payload = IncomingWebhookPayload(
            event_type="test",
            data={},
        )

        event = await receiver.receive(
            payload=payload,
            raw_body=raw_body,
            signature=sig,
        )

        assert event.type == "test"

    @pytest.mark.asyncio
    async def test_receive_invalid_signature_raises(self):
        """Test ricezione con signature invalida solleva errore."""
        receiver = WebhookReceiver(secret="testsecret")

        payload = IncomingWebhookPayload(
            event_type="test",
            data={},
        )

        with pytest.raises(ValueError, match="Invalid webhook signature"):
            await receiver.receive(
                payload=payload,
                raw_body=b"test",
                signature="invalid",
            )

    def test_on_event_decorator(self):
        """Test decorator on_event."""
        receiver = WebhookReceiver()

        @receiver.on_event("job.completed")
        def handler(event):
            pass

        assert "job.completed" in receiver._event_handlers
        assert len(receiver._event_handlers["job.completed"]) == 1


# --- Dispatcher Tests ---


class TestWebhookDispatcher:
    """Test per WebhookDispatcher."""

    def test_sign_payload(self):
        """Test firma payload."""
        dispatcher = WebhookDispatcher()
        payload = b'{"test": "data"}'

        sig = dispatcher.sign_payload(payload, "mysecret")
        assert sig.startswith("sha256=")

    @pytest.mark.asyncio
    async def test_dispatch_success(self):
        """Test dispatch con successo."""
        dispatcher = WebhookDispatcher()

        config = WebhookConfig(
            id="cfg-123",
            name="Test",
            url="https://httpbin.org/post",
            events=["test"],
            secret="secret",
        )

        event = WebhookEvent(
            id="evt-123",
            type="test",
            source="test",
            payload={"key": "value"},
        )

        # Mock aiohttp - use proper async context managers
        with patch("me4brain.core.webhooks.dispatcher.aiohttp.ClientSession") as mock_session_cls:
            # Create mock response
            mock_response = MagicMock()
            mock_response.status = 200

            # Create async context manager for response
            async def mock_response_aenter(self_inner):
                return mock_response

            mock_response.__aenter__ = mock_response_aenter
            mock_response.__aexit__ = AsyncMock(return_value=None)

            # Create mock session
            mock_session = MagicMock()
            mock_session.post = MagicMock(return_value=mock_response)

            # Create async context manager for session
            async def mock_session_aenter(self_inner):
                return mock_session

            mock_session.__aenter__ = mock_session_aenter
            mock_session.__aexit__ = AsyncMock(return_value=None)

            mock_session_cls.return_value = mock_session

            delivery = await dispatcher.dispatch(config, event)

            assert delivery.status == "success"
            assert delivery.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_retry_on_failure(self):
        """Test retry su fallimento."""
        dispatcher = WebhookDispatcher()

        config = WebhookConfig(
            id="cfg-123",
            name="Test",
            url="https://example.com/fail",
            events=["test"],
            secret="secret",
            retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=[0]),
        )

        event = WebhookEvent(
            id="evt-123",
            type="test",
            source="test",
            payload={},
        )

        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_response.text = AsyncMock(return_value="Server Error")
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock()

            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()

            mock_session.return_value = mock_client

            delivery = await dispatcher.dispatch(config, event)

            assert delivery.status == "failed"
            assert delivery.attempt == 2  # 2 tentativi

    @pytest.mark.asyncio
    async def test_get_failed_count_no_redis(self):
        """Test count senza Redis."""
        dispatcher = WebhookDispatcher()
        count = await dispatcher.get_failed_count()
        assert count == 0
