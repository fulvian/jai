import pytest
import time
from unittest.mock import MagicMock, patch
from me4brain.utils.metrics import MetricsService, track_latency


def test_metrics_service_calls():
    # Test record methods
    with (
        patch("me4brain.utils.metrics.REQUEST_LATENCY.labels") as mock_req,
        patch("me4brain.utils.metrics.LLM_TOKENS_TOTAL.labels") as mock_tokens,
        patch("me4brain.utils.metrics.MEMORY_HITS_TOTAL.labels") as mock_hits,
    ):
        MetricsService.record_request_latency("GET", "/test", "t1", 0.5)
        mock_req.assert_called_with(method="GET", endpoint="/test", tenant_id="t1")

        MetricsService.record_llm_usage("gpt-4", "t1", 10, 20)
        assert mock_tokens.call_count == 2

        MetricsService.record_memory_hit("episodic", "t1")
        mock_hits.assert_called_with(source="episodic", tenant_id="t1")


@pytest.mark.asyncio
async def test_track_latency_decorator():
    @track_latency("POST", "/invoke", "t2")
    async def fast_function():
        return "done"

    with patch("me4brain.utils.metrics.MetricsService.record_request_latency") as mock_record:
        result = await fast_function()
        assert result == "done"
        mock_record.assert_called_once()
        args, kwargs = mock_record.call_args
        assert args[0] == "POST"
        assert args[1] == "/invoke"
        assert args[2] == "t2"
        assert args[3] >= 0
