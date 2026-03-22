"""Notification Dispatcher.

Gestisce invio notifiche multi-canale.
"""

import os
from typing import Any

import httpx
import structlog

from backend.proactive.monitors import NotifyChannel

logger = structlog.get_logger(__name__)


class NotificationDispatcher:
    """Dispatcher per notifiche multi-canale.

    Supporta: WebSocket (via Gateway), Telegram, Email, Slack.
    """

    def __init__(
        self,
        telegram_bot_token: str | None = None,
        slack_webhook_url: str | None = None,
        smtp_config: dict[str, Any] | None = None,
        gateway_url: str | None = None,
    ):
        """Inizializza dispatcher.

        Args:
            telegram_bot_token: Token bot Telegram
            slack_webhook_url: Webhook URL Slack
            smtp_config: Configurazione SMTP per email
            gateway_url: URL Gateway per push WebSocket (default: http://localhost:3030)
        """
        self.telegram_token = telegram_bot_token
        self.slack_webhook = slack_webhook_url
        self.smtp_config = smtp_config or {}
        self.gateway_url = gateway_url or os.getenv("GATEWAY_URL", "http://localhost:3030")

        # HTTP client
        self._http_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy init HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def close(self) -> None:
        """Chiude risorse."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    # =========================================================================
    # Main Dispatch
    # =========================================================================

    async def dispatch(
        self,
        user_id: str,
        channels: list[NotifyChannel],
        title: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, bool]:
        """Invia notifica su multipli canali.

        Args:
            user_id: ID utente destinatario
            channels: Lista canali su cui inviare
            title: Titolo notifica
            message: Corpo messaggio (markdown supportato)
            data: Dati aggiuntivi opzionali

        Returns:
            Dict con risultato per canale
        """
        results: dict[str, bool] = {}

        for channel in channels:
            try:
                if channel == NotifyChannel.WEB:
                    results["web"] = await self._send_websocket(user_id, title, message, data)
                elif channel == NotifyChannel.TELEGRAM:
                    results["telegram"] = await self._send_telegram(user_id, title, message)
                elif channel == NotifyChannel.SLACK:
                    results["slack"] = await self._send_slack(title, message)
                elif channel == NotifyChannel.EMAIL:
                    results["email"] = await self._send_email(user_id, title, message)
                elif channel == NotifyChannel.WHATSAPP:
                    # WhatsApp non ancora implementato
                    results["whatsapp"] = False
                    logger.warning("whatsapp_not_implemented")

            except Exception as e:
                logger.error(
                    "dispatch_channel_error",
                    channel=channel.value,
                    error=str(e),
                )
                results[channel.value] = False

        logger.info(
            "dispatch_complete",
            user_id=user_id,
            channels=[c.value for c in channels],
            results=results,
        )

        return results

    # =========================================================================
    # Channel Implementations
    # =========================================================================

    async def _send_websocket(
        self,
        user_id: str,
        title: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> bool:
        """Invia notifica via WebSocket al frontend tramite Gateway.

        Chiama POST /api/push/monitor/alert sul gateway che
        inoltra il messaggio via WebSocket all'utente connesso.
        """
        client = await self._get_client()

        # Estrai dati monitor dal data payload
        monitor_data = data or {}
        alert_payload = {
            "userId": user_id,
            "alert": {
                "monitorId": monitor_data.get("monitor_id", "unknown"),
                "monitorName": title.replace("📈 Alert ", "").replace("📉 Alert ", ""),
                "type": monitor_data.get("result", {}).get("type", "autonomous"),
                "title": title,
                "message": message,
                "recommendation": monitor_data.get("result", {})
                .get("decision", {})
                .get("recommendation"),
                "confidence": monitor_data.get("result", {}).get("decision", {}).get("confidence"),
                "ticker": monitor_data.get("result", {}).get("ticker"),
                "triggeredAt": int(self._get_timestamp_ms()),
            },
        }

        try:
            response = await client.post(
                f"{self.gateway_url}/api/push/monitor/alert",
                json=alert_payload,
            )

            if response.status_code == 200:
                result = response.json()
                sent_count = result.get("sent", 0)
                logger.info(
                    "websocket_notification_sent_via_gateway",
                    user_id=user_id,
                    sent=sent_count,
                )
                return sent_count > 0
            else:
                logger.warning(
                    "gateway_push_error",
                    status=response.status_code,
                    response=response.text,
                )
                return False

        except httpx.ConnectError:
            logger.warning(
                "gateway_not_available",
                gateway_url=self.gateway_url,
                user_id=user_id,
            )
            return False

        except Exception as e:
            logger.error("gateway_push_exception", error=str(e))
            return False

    async def _send_telegram(
        self,
        user_id: str,
        title: str,
        message: str,
    ) -> bool:
        """Invia notifica via Telegram."""
        if not self.telegram_token:
            logger.warning("telegram_token_not_configured")
            return False

        # Lookup telegram chat_id per user
        # TODO: Implementare mapping user_id → telegram_chat_id
        chat_id = await self._get_telegram_chat_id(user_id)
        if not chat_id:
            logger.warning("telegram_chat_id_not_found", user_id=user_id)
            return False

        client = await self._get_client()

        try:
            # Format message per Telegram (Markdown)
            text = f"*{title}*\n\n{message}"

            response = await client.post(
                f"https://api.telegram.org/bot{self.telegram_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
            )

            if response.status_code == 200:
                logger.info("telegram_notification_sent", chat_id=chat_id)
                return True
            else:
                logger.warning(
                    "telegram_send_error",
                    status=response.status_code,
                    response=response.text,
                )

        except Exception as e:
            logger.error("telegram_send_exception", error=str(e))

        return False

    async def _send_slack(
        self,
        title: str,
        message: str,
    ) -> bool:
        """Invia notifica via Slack webhook."""
        if not self.slack_webhook:
            logger.warning("slack_webhook_not_configured")
            return False

        client = await self._get_client()

        try:
            response = await client.post(
                self.slack_webhook,
                json={
                    "text": f"*{title}*\n{message}",
                    "blocks": [
                        {
                            "type": "header",
                            "text": {"type": "plain_text", "text": title},
                        },
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": message},
                        },
                    ],
                },
            )

            if response.status_code == 200:
                logger.info("slack_notification_sent")
                return True
            else:
                logger.warning(
                    "slack_send_error",
                    status=response.status_code,
                )

        except Exception as e:
            logger.error("slack_send_exception", error=str(e))

        return False

    async def _send_email(
        self,
        user_id: str,
        title: str,
        message: str,
    ) -> bool:
        """Invia notifica via email."""
        if not self.smtp_config:
            logger.warning("smtp_not_configured")
            return False

        # TODO: Implementare invio email via SMTP
        # Richiede aiosmtplib e configurazione SMTP

        logger.warning("email_send_not_implemented")
        return False

    # =========================================================================
    # Helpers
    # =========================================================================

    async def _get_telegram_chat_id(self, user_id: str) -> str | None:
        """Lookup telegram chat_id per user.

        TODO: Implementare storage mapping user_id → telegram_chat_id
        """
        # Placeholder: in futuro lookup da database/Redis
        return None

    def _get_timestamp(self) -> str:
        """Ritorna timestamp ISO corrente."""
        from datetime import datetime

        return datetime.utcnow().isoformat() + "Z"

    def _get_timestamp_ms(self) -> int:
        """Ritorna timestamp Unix in millisecondi."""
        import time

        return int(time.time() * 1000)


# =============================================================================
# Message Formatters
# =============================================================================


def format_stock_alert(
    ticker: str,
    recommendation: str,
    confidence: int,
    reasoning: str,
    key_factors: list[str],
    suggested_action: str | None = None,
) -> tuple[str, str]:
    """Formatta alert stock per notifiche.

    Returns:
        Tuple (title, message)
    """
    emoji_map = {
        "BUY": "📈",
        "SELL": "📉",
        "HOLD": "➖",
        "WAIT": "⏳",
        "ALERT": "🔔",
    }
    emoji = emoji_map.get(recommendation, "📊")

    title = f"{emoji} Alert {ticker}"

    message = f"""**Raccomandazione**: {recommendation}
**Confidenza**: {confidence}%

**Motivazione**: {reasoning}

**Fattori chiave**:
{chr(10).join(f"• {f}" for f in key_factors)}"""

    if suggested_action:
        message += f"\n\n**Azione suggerita**: {suggested_action}"

    return title, message
