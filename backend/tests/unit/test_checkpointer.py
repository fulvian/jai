"""Test Checkpointer Module.

Test per il modulo core/checkpointer.py che gestisce
la persistenza dello stato LangGraph su PostgreSQL.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCheckpointer:
    """Test suite per checkpointer PostgreSQL."""

    @pytest.mark.asyncio
    async def test_create_checkpointer_success(self) -> None:
        """Verifica creazione checkpointer con mock PostgresSaver."""
        mock_saver = AsyncMock()
        mock_saver.setup = AsyncMock()

        with (
            patch("me4brain.core.checkpointer.get_settings") as mock_settings,
            patch(
                "me4brain.core.checkpointer.AsyncPostgresSaver.from_conn_string",
                return_value=mock_saver,
            ) as mock_from_conn,
        ):
            settings = MagicMock()
            settings.postgres_dsn = "postgresql://user:pass@localhost:5432/db"
            settings.postgres_host = "localhost"
            settings.postgres_port = 5432
            settings.postgres_db = "me4brain"
            mock_settings.return_value = settings

            from me4brain.core.checkpointer import create_checkpointer

            result = await create_checkpointer()

            mock_from_conn.assert_called_once_with(settings.postgres_dsn)
            mock_saver.setup.assert_called_once()
            assert result == mock_saver

    @pytest.mark.asyncio
    async def test_get_checkpointer_singleton(self) -> None:
        """Verifica lazy init singleton per checkpointer."""
        import me4brain.core.checkpointer as checkpointer_module

        # Reset stato globale
        checkpointer_module._checkpointer = None

        mock_saver = AsyncMock()
        mock_saver.setup = AsyncMock()

        with (
            patch("me4brain.core.checkpointer.get_settings") as mock_settings,
            patch(
                "me4brain.core.checkpointer.AsyncPostgresSaver.from_conn_string",
                return_value=mock_saver,
            ),
        ):
            settings = MagicMock()
            settings.postgres_dsn = "postgresql://user:pass@localhost:5432/db"
            settings.postgres_host = "localhost"
            settings.postgres_port = 5432
            settings.postgres_db = "me4brain"
            mock_settings.return_value = settings

            from me4brain.core.checkpointer import get_checkpointer

            # Prima chiamata: crea
            result1 = await get_checkpointer()

            # Seconda chiamata: riusa
            result2 = await get_checkpointer()

            assert result1 is result2
            # Create deve essere chiamato una sola volta
            mock_saver.setup.assert_called_once()

        # Cleanup
        checkpointer_module._checkpointer = None

    @pytest.mark.asyncio
    async def test_close_checkpointer(self) -> None:
        """Verifica chiusura e reset del checkpointer globale."""
        import me4brain.core.checkpointer as checkpointer_module

        # Setup: simula checkpointer esistente
        mock_saver = AsyncMock()
        checkpointer_module._checkpointer = mock_saver

        from me4brain.core.checkpointer import close_checkpointer

        await close_checkpointer()

        # Verifica che sia stato resettato
        assert checkpointer_module._checkpointer is None

    @pytest.mark.asyncio
    async def test_close_checkpointer_when_none(self) -> None:
        """Verifica che close non generi errori se già None."""
        import me4brain.core.checkpointer as checkpointer_module

        checkpointer_module._checkpointer = None

        from me4brain.core.checkpointer import close_checkpointer

        # Non deve sollevare eccezioni
        await close_checkpointer()

        assert checkpointer_module._checkpointer is None
