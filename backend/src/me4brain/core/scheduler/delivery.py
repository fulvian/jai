"""Delivery Service - Consegna risultati job via multi-channel."""

from __future__ import annotations

import asyncio

import aiohttp
import structlog

from me4brain.core.scheduler.types import DeliveryConfig

logger = structlog.get_logger(__name__)


class DeliveryService:
    """
    Servizio per consegna risultati job.

    Supporta:
    - log: Logging strutturato
    - webhook: HTTP POST a URL configurabile
    """

    # Retry config per webhook
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 5, 15]  # secondi

    def __init__(self, timeout: int = 30):
        """
        Inizializza servizio.

        Args:
            timeout: Timeout HTTP in secondi
        """
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    async def deliver(
        self,
        config: DeliveryConfig,
        job_name: str,
        result: dict,
        success: bool,
    ) -> dict[str, bool]:
        """
        Consegna risultato su tutti i canali configurati.

        Args:
            config: Configurazione delivery
            job_name: Nome del job
            result: Risultato esecuzione
            success: Esito esecuzione

        Returns:
            Dict con esito per ogni canale
        """
        outcomes: dict[str, bool] = {}

        for channel in config.channels:
            try:
                if channel == "log":
                    await self._deliver_log(job_name, result, success)
                    outcomes["log"] = True

                elif channel == "webhook":
                    if config.webhook_url:
                        delivered = await self._deliver_webhook(
                            config.webhook_url,
                            config.webhook_headers,
                            job_name,
                            result,
                            success,
                        )
                        outcomes["webhook"] = delivered
                    else:
                        logger.warning("webhook_url_missing", job=job_name)
                        outcomes["webhook"] = False

                else:
                    logger.warning("unknown_channel", channel=channel)
                    outcomes[channel] = False

            except Exception as e:
                logger.error(
                    "delivery_error",
                    channel=channel,
                    job=job_name,
                    error=str(e),
                )
                outcomes[channel] = False

        return outcomes

    async def _deliver_log(
        self,
        job_name: str,
        result: dict,
        success: bool,
    ) -> None:
        """Log del risultato."""
        log_level = "info" if success else "warning"

        getattr(logger, log_level)(
            "job_result_delivered",
            channel="log",
            job=job_name,
            success=success,
            result_keys=list(result.keys()) if result else [],
        )

    async def _deliver_webhook(
        self,
        url: str,
        headers: dict[str, str],
        job_name: str,
        result: dict,
        success: bool,
    ) -> bool:
        """
        Consegna via webhook HTTP POST.

        Args:
            url: URL webhook
            headers: Headers aggiuntivi
            job_name: Nome job
            result: Risultato
            success: Esito

        Returns:
            True se consegnato con successo
        """
        payload = {
            "job_name": job_name,
            "success": success,
            "result": result,
            "timestamp": asyncio.get_event_loop().time(),
        }

        default_headers = {
            "Content-Type": "application/json",
            "User-Agent": "Me4BrAIn-Scheduler/1.0",
        }
        all_headers = {**default_headers, **headers}

        for attempt, delay in enumerate(self.RETRY_DELAYS, 1):
            try:
                async with aiohttp.ClientSession(timeout=self.timeout) as session:
                    async with session.post(
                        url,
                        json=payload,
                        headers=all_headers,
                    ) as response:
                        if response.status < 400:
                            logger.info(
                                "webhook_delivered",
                                url=url,
                                job=job_name,
                                status=response.status,
                                attempt=attempt,
                            )
                            return True
                        else:
                            logger.warning(
                                "webhook_error_response",
                                url=url,
                                status=response.status,
                                attempt=attempt,
                            )

            except TimeoutError:
                logger.warning(
                    "webhook_timeout",
                    url=url,
                    attempt=attempt,
                    max_attempts=self.MAX_RETRIES,
                )
            except aiohttp.ClientError as e:
                logger.warning(
                    "webhook_client_error",
                    url=url,
                    error=str(e),
                    attempt=attempt,
                )
            except Exception as e:
                logger.error(
                    "webhook_unexpected_error",
                    url=url,
                    error=str(e),
                    attempt=attempt,
                )

            # Retry se non ultimo tentativo
            if attempt < self.MAX_RETRIES:
                await asyncio.sleep(delay)

        logger.error(
            "webhook_delivery_failed",
            url=url,
            job=job_name,
            attempts=self.MAX_RETRIES,
        )
        return False


# Singleton
_delivery_service: DeliveryService | None = None


def get_delivery_service() -> DeliveryService:
    """Ottiene o crea delivery service."""
    global _delivery_service
    if _delivery_service is None:
        _delivery_service = DeliveryService()
    return _delivery_service
