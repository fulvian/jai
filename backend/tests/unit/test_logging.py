import pytest
import structlog
import logging
import json
import io
from me4brain.utils.logging import configure_logging


def test_configure_logging():
    # Test that it runs without error
    configure_logging("DEBUG")
    logger = structlog.get_logger("test")
    assert logger is not None


def test_json_logging_format():
    # Capture output
    log_output = io.StringIO()

    # Configure structlog to write to our string buffer
    structlog.configure(
        processors=[structlog.processors.JSONRenderer()],
        logger_factory=structlog.PrintLoggerFactory(log_output),
    )

    logger = structlog.get_logger("test_json")
    logger.info("test_message", key="value")

    output = log_output.getvalue()
    log_data = json.loads(output)

    assert log_data["event"] == "test_message"
    assert log_data["key"] == "value"
