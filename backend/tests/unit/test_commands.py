"""Unit tests per Slash Commands (M4)."""

import pytest

from me4brain.engine.commands import ParsedCommand, SlashCommands


class TestSlashCommands:
    """Test per SlashCommands."""

    def test_is_command_true(self):
        """Test riconoscimento comando."""
        cmds = SlashCommands()
        assert cmds.is_command("/status") is True
        assert cmds.is_command("/forget my password") is True
        assert cmds.is_command("/help") is True

    def test_is_command_false(self):
        """Test non-comandi."""
        cmds = SlashCommands()
        assert cmds.is_command("hello world") is False
        assert cmds.is_command("what is /status?") is False
        assert cmds.is_command("") is False

    def test_parse_status(self):
        """Test parsing /status."""
        cmds = SlashCommands()
        result = cmds.parse("/status")

        assert result is not None
        assert result.command == "status"
        assert result.args == ""

    def test_parse_forget_with_args(self):
        """Test parsing /forget con argomenti."""
        cmds = SlashCommands()
        result = cmds.parse("/forget my bank password")

        assert result is not None
        assert result.command == "forget"
        assert result.args == "my bank password"

    def test_parse_help(self):
        """Test parsing /help."""
        cmds = SlashCommands()
        result = cmds.parse("/help")

        assert result is not None
        assert result.command == "help"

    def test_parse_unknown_command(self):
        """Test comando sconosciuto."""
        cmds = SlashCommands()
        result = cmds.parse("/unknown_command args")

        assert result is None  # Non è nei comandi registrati

    def test_parse_not_a_command(self):
        """Test messaggio non comando."""
        cmds = SlashCommands()
        result = cmds.parse("just a normal message")

        assert result is None

    @pytest.mark.asyncio
    async def test_execute_status(self):
        """Test esecuzione /status."""
        cmds = SlashCommands()
        result = await cmds.execute("/status", "session-123")

        assert result is not None
        assert "Session Status" in result
        assert "session-123" in result

    @pytest.mark.asyncio
    async def test_execute_help(self):
        """Test esecuzione /help."""
        cmds = SlashCommands()
        result = await cmds.execute("/help", "session-123")

        assert result is not None
        assert "/status" in result
        assert "/forget" in result
        assert "/help" in result

    @pytest.mark.asyncio
    async def test_execute_forget_without_topic(self):
        """Test /forget senza topic."""
        cmds = SlashCommands()
        result = await cmds.execute("/forget", "session-123")

        assert result is not None
        assert "Uso:" in result
        assert "/forget <topic>" in result

    @pytest.mark.asyncio
    async def test_execute_forget_with_topic(self):
        """Test /forget con topic."""
        cmds = SlashCommands()
        result = await cmds.execute("/forget my password", "session-123")

        assert result is not None
        assert "Topic dimenticato" in result
        assert "my password" in result

    @pytest.mark.asyncio
    async def test_execute_unknown_command(self):
        """Test comando sconosciuto."""
        cmds = SlashCommands()
        result = await cmds.execute("/unknown", "session-123")

        assert result is None  # Non è un comando valido

    @pytest.mark.asyncio
    async def test_execute_normal_message(self):
        """Test messaggio normale (non comando)."""
        cmds = SlashCommands()
        result = await cmds.execute("ciao come stai?", "session-123")

        assert result is None


class TestParsedCommand:
    """Test per ParsedCommand dataclass."""

    def test_create_parsed_command(self):
        """Test creazione ParsedCommand."""
        cmd = ParsedCommand(command="status", args="")
        assert cmd.command == "status"
        assert cmd.args == ""

    def test_parsed_command_with_args(self):
        """Test ParsedCommand con argomenti."""
        cmd = ParsedCommand(command="forget", args="sensitive data")
        assert cmd.command == "forget"
        assert cmd.args == "sensitive data"
