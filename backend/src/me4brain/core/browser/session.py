"""Browser Session - Wrapper Stagehand per interazione browser."""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import structlog

from me4brain.core.browser.types import (
    ActionType,
    BrowserAction,
    BrowserActionResult,
    BrowserSession,
    BrowserStatus,
)

logger = structlog.get_logger(__name__)

# Screenshot directory
SCREENSHOT_DIR = Path("/tmp/me4brain/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


class BrowserSessionWrapper:
    """
    Wrapper per sessione browser con Stagehand.

    Core API:
    - navigate(url): Go to URL
    - act(instruction): Natural language action
    - extract(instruction, schema): Structured data extraction
    - observe(): Get page state
    - screenshot(): Capture view
    """

    def __init__(self, session: BrowserSession):
        """
        Inizializza wrapper.

        Args:
            session: Metadata sessione
        """
        self.session = session
        self._stagehand = None
        self._page = None
        self._initialized = False

    async def initialize(self) -> None:
        """Inizializza browser e Stagehand."""
        if self._initialized:
            return

        try:
            # Import Stagehand
            from stagehand import Stagehand

            # Configurazione
            config = self.session.config

            self._stagehand = Stagehand(
                headless=config.headless,
                slow_mo=config.slow_mo_ms if config.slow_mo_ms > 0 else None,
                timeout=config.timeout_ms,
            )

            # Get page
            self._page = await self._stagehand.page

            self.session.status = BrowserStatus.READY
            self._initialized = True

            logger.info(
                "browser_session_initialized",
                session_id=self.session.id,
                headless=config.headless,
            )

        except ImportError:
            # Fallback a Playwright puro se Stagehand non disponibile
            logger.warning("stagehand_not_available_using_playwright")
            await self._init_playwright_fallback()

        except Exception as e:
            self.session.status = BrowserStatus.ERROR
            logger.error("browser_init_error", error=str(e))
            raise

    async def _init_playwright_fallback(self) -> None:
        """Inizializza con Playwright puro (fallback)."""
        from playwright.async_api import async_playwright

        config = self.session.config

        self._playwright = await async_playwright().start()

        browser_type = getattr(self._playwright, config.browser_type.value)
        self._browser = await browser_type.launch(
            headless=config.headless,
            slow_mo=config.slow_mo_ms if config.slow_mo_ms > 0 else None,
        )

        self._context = await self._browser.new_context(
            viewport={
                "width": config.viewport_width,
                "height": config.viewport_height,
            },
        )

        self._page = await self._context.new_page()
        self._initialized = True

    async def navigate(self, url: str, wait_until: str = "load") -> BrowserActionResult:
        """
        Naviga a URL.

        Args:
            url: URL destinazione
            wait_until: Evento da attendere

        Returns:
            Risultato navigazione
        """
        action_id = str(uuid.uuid4())[:8]
        start = datetime.now()

        try:
            await self._page.goto(url, wait_until=wait_until)

            self.session.current_url = self._page.url
            self.session.current_title = await self._page.title()
            self.session.action_count += 1
            self.session.last_action_at = datetime.now()

            duration = int((datetime.now() - start).total_seconds() * 1000)

            logger.info(
                "browser_navigate",
                session_id=self.session.id,
                url=url,
                duration_ms=duration,
            )

            return BrowserActionResult(
                action_id=action_id,
                success=True,
                duration_ms=duration,
                url=self.session.current_url,
                title=self.session.current_title,
            )

        except Exception as e:
            self.session.error_count += 1
            return BrowserActionResult(
                action_id=action_id,
                success=False,
                duration_ms=0,
                error=str(e),
            )

    async def act(self, instruction: str) -> BrowserActionResult:
        """
        Esegue azione con natural language (Stagehand).

        Args:
            instruction: Descrizione azione

        Returns:
            Risultato azione
        """
        action_id = str(uuid.uuid4())[:8]
        start = datetime.now()

        try:
            if self._stagehand:
                # Usa Stagehand act()
                result = await self._stagehand.act(instruction)
            else:
                # Fallback: parsing semplice
                result = await self._act_fallback(instruction)

            self.session.action_count += 1
            self.session.last_action_at = datetime.now()
            duration = int((datetime.now() - start).total_seconds() * 1000)

            # Update page state
            self.session.current_url = self._page.url
            self.session.current_title = await self._page.title()

            logger.info(
                "browser_act",
                session_id=self.session.id,
                instruction=instruction[:50],
                duration_ms=duration,
            )

            return BrowserActionResult(
                action_id=action_id,
                success=True,
                duration_ms=duration,
                data={"result": str(result)} if result else None,
                url=self.session.current_url,
            )

        except Exception as e:
            self.session.error_count += 1
            logger.error("browser_act_error", error=str(e))
            return BrowserActionResult(
                action_id=action_id,
                success=False,
                duration_ms=0,
                error=str(e),
            )

    async def _act_fallback(self, instruction: str) -> Any:
        """Fallback per act() senza Stagehand."""
        # Pattern matching basilare
        instr_lower = instruction.lower()

        if "click" in instr_lower:
            # Prova a estrarre target
            if "button" in instr_lower:
                await self._page.click("button")
            elif "link" in instr_lower:
                await self._page.click("a")

        elif "type" in instr_lower or "fill" in instr_lower:
            # Cerca input field
            await self._page.fill(
                "input", instruction.split('"')[1] if '"' in instruction else ""
            )

        elif "scroll" in instr_lower:
            await self._page.evaluate("window.scrollBy(0, 500)")

        return None

    async def extract(
        self,
        instruction: str,
        schema: Optional[dict] = None,
    ) -> BrowserActionResult:
        """
        Estrae dati strutturati (Stagehand).

        Args:
            instruction: Cosa estrarre
            schema: JSON Schema output

        Returns:
            Risultato con dati
        """
        action_id = str(uuid.uuid4())[:8]
        start = datetime.now()

        try:
            if self._stagehand:
                # Usa Stagehand extract()
                if schema:
                    result = await self._stagehand.extract(instruction, schema=schema)
                else:
                    result = await self._stagehand.extract(instruction)
            else:
                # Fallback: estrai testo
                result = await self._page.inner_text("body")

            duration = int((datetime.now() - start).total_seconds() * 1000)
            self.session.action_count += 1

            logger.info(
                "browser_extract",
                session_id=self.session.id,
                instruction=instruction[:50],
            )

            return BrowserActionResult(
                action_id=action_id,
                success=True,
                duration_ms=duration,
                data={"extracted": result},
            )

        except Exception as e:
            return BrowserActionResult(
                action_id=action_id,
                success=False,
                duration_ms=0,
                error=str(e),
            )

    async def observe(self) -> BrowserActionResult:
        """
        Osserva stato pagina.

        Returns:
            Stato corrente con elementi
        """
        action_id = str(uuid.uuid4())[:8]

        try:
            if self._stagehand:
                # Usa Stagehand observe()
                observations = await self._stagehand.observe()
            else:
                # Fallback: informazioni base
                observations = {
                    "url": self._page.url,
                    "title": await self._page.title(),
                    "viewport": await self._page.viewport_size(),
                }

            return BrowserActionResult(
                action_id=action_id,
                success=True,
                duration_ms=0,
                data=observations,
                url=self._page.url,
            )

        except Exception as e:
            return BrowserActionResult(
                action_id=action_id,
                success=False,
                duration_ms=0,
                error=str(e),
            )

    async def screenshot(self, full_page: bool = False) -> BrowserActionResult:
        """
        Cattura screenshot.

        Args:
            full_page: Cattura pagina intera

        Returns:
            Risultato con path screenshot
        """
        action_id = str(uuid.uuid4())[:8]

        try:
            filename = f"{self.session.id}_{action_id}.png"
            path = SCREENSHOT_DIR / filename

            await self._page.screenshot(path=str(path), full_page=full_page)

            logger.info(
                "browser_screenshot",
                session_id=self.session.id,
                path=str(path),
            )

            return BrowserActionResult(
                action_id=action_id,
                success=True,
                duration_ms=0,
                screenshot_path=str(path),
            )

        except Exception as e:
            return BrowserActionResult(
                action_id=action_id,
                success=False,
                duration_ms=0,
                error=str(e),
            )

    async def close(self) -> None:
        """Chiude browser session."""
        try:
            if self._stagehand:
                await self._stagehand.close()
            elif hasattr(self, "_browser"):
                await self._browser.close()
                await self._playwright.stop()

            self.session.status = BrowserStatus.CLOSED
            self._initialized = False

            logger.info("browser_session_closed", session_id=self.session.id)

        except Exception as e:
            logger.error("browser_close_error", error=str(e))

    @property
    def is_ready(self) -> bool:
        """Check se sessione pronta."""
        return self._initialized and self.session.status == BrowserStatus.READY
