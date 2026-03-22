# Error Handling and Fallback Behavior

## Overview

The UnifiedIntentAnalyzer implements comprehensive error handling with safe fallback behavior to ensure the system remains operational even when errors occur.

## Error Scenarios

### Scenario 1: LLM API Unavailable

**Condition**: LLM API is down or unreachable

**Fallback Behavior**:
```python
IntentAnalysis(
    intent=IntentType.TOOL_REQUIRED,
    domains=["general"],
    complexity=QueryComplexity.SIMPLE,
    confidence=0.5,
    reasoning="llm_api_failed"
)
```

**Rationale**: Assume tool_required for safety (better to try tools than miss them)

**Recovery**:
1. Log error with structured data
2. Increment LLM API failure counter
3. Return fallback analysis
4. Trigger alert if failure rate > 10%

**Example**:
```python
try:
    response = await llm_client.generate_response(request)
except Exception as e:
    logger.error("llm_api_failed", error=str(e))
    monitor.record_error("llm_api_failure")
    return self._fallback_analysis("llm_api_failed")
```

### Scenario 2: Invalid JSON Response

**Condition**: LLM returns invalid JSON or unexpected format

**Fallback Behavior**:
```python
IntentAnalysis(
    intent=IntentType.TOOL_REQUIRED,
    domains=["general"],
    complexity=QueryComplexity.SIMPLE,
    confidence=0.5,
    reasoning="json_parse_failed"
)
```

**Rationale**: LLM may have formatting issues; fallback to safe default

**Recovery**:
1. Log warning with response preview
2. Increment JSON parse failure counter
3. Return fallback analysis
4. Monitor for patterns in failures

**Example**:
```python
try:
    result = json.loads(response.choices[0].message.content)
except json.JSONDecodeError as e:
    logger.warning(
        "json_parse_failed",
        error=str(e),
        response_preview=response.choices[0].message.content[:100]
    )
    monitor.record_error("json_parse_failure")
    return self._fallback_analysis("json_parse_failed")
```

### Scenario 3: Empty Query

**Condition**: User submits empty or whitespace-only query

**Fallback Behavior**:
```python
IntentAnalysis(
    intent=IntentType.CONVERSATIONAL,
    domains=[],
    complexity=QueryComplexity.SIMPLE,
    confidence=1.0,
    reasoning="empty_query"
)
```

**Rationale**: Empty query is conversational (no tools needed)

**Recovery**:
1. Log warning
2. Return conversational intent
3. No error counter increment (expected behavior)

**Example**:
```python
if not query or not query.strip():
    logger.warning("empty_query_received")
    return IntentAnalysis(
        intent=IntentType.CONVERSATIONAL,
        domains=[],
        complexity=QueryComplexity.SIMPLE,
        confidence=1.0,
        reasoning="empty_query"
    )
```

### Scenario 4: Invalid Domain in Response

**Condition**: LLM returns domain not in available domains list

**Fallback Behavior**:
```python
# Filter out invalid domains, keep valid ones
valid_domains = [d for d in response_domains if d in AVAILABLE_DOMAINS]

# If no valid domains remain, add "general"
if not valid_domains:
    valid_domains = ["general"]
```

**Rationale**: Prevent routing to non-existent domains

**Recovery**:
1. Log warning with invalid domains
2. Filter to valid domains only
3. Add "general" if no valid domains
4. Increment invalid domain filter counter

**Example**:
```python
valid_domains = [d for d in validated.domains if d in self.AVAILABLE_DOMAINS]

if validated.intent == IntentType.TOOL_REQUIRED and not valid_domains:
    logger.warning(
        "no_valid_domains",
        requested_domains=validated.domains,
        available_domains=self.AVAILABLE_DOMAINS
    )
    valid_domains = ["general"]
    monitor.record_error("invalid_domain_filter")
```

### Scenario 5: Validation Error

**Condition**: Response fails Pydantic validation

**Fallback Behavior**:
```python
IntentAnalysis(
    intent=IntentType.TOOL_REQUIRED,
    domains=["general"],
    complexity=QueryComplexity.SIMPLE,
    confidence=0.5,
    reasoning="validation_failed"
)
```

**Rationale**: Response structure is invalid; use safe default

**Recovery**:
1. Log warning with validation error
2. Return fallback analysis
3. Monitor for patterns

**Example**:
```python
try:
    validated = IntentAnalysisModel(**result)
except ValueError as e:
    logger.warning(
        "validation_failed",
        error=str(e),
        response=result
    )
    return self._fallback_analysis("validation_failed")
```

### Scenario 6: Query Too Long

**Condition**: Query exceeds 1000 character limit

**Fallback Behavior**:
```python
# Truncate query to 1000 characters
query = query[:1000]
logger.warning(
    "query_truncated",
    original_length=len(query),
    truncated_length=1000
)
# Continue with truncated query
```

**Rationale**: Prevent LLM token limit issues

**Recovery**:
1. Log warning
2. Truncate query
3. Continue analysis with truncated query
4. No error counter increment

**Example**:
```python
if len(query) > 1000:
    query = query[:1000]
    logger.warning(
        "query_truncated",
        original_length=len(query),
        truncated_length=1000
    )
```

### Scenario 7: Empty LLM Response

**Condition**: LLM returns empty response

**Fallback Behavior**:
```python
IntentAnalysis(
    intent=IntentType.TOOL_REQUIRED,
    domains=["general"],
    complexity=QueryComplexity.SIMPLE,
    confidence=0.5,
    reasoning="empty_response"
)
```

**Rationale**: No response means we can't classify; use safe default

**Recovery**:
1. Log warning
2. Return fallback analysis
3. Monitor for patterns

**Example**:
```python
if not response.choices or not response.choices[0].message.content:
    logger.warning("empty_response_received")
    return self._fallback_analysis("empty_response")
```

## Error Handling Strategies

### Strategy 1: Fail-Safe Defaults

Always fallback to `tool_required` with `general` domain:

```python
# Safe default: assume tools might be needed
IntentAnalysis(
    intent=IntentType.TOOL_REQUIRED,
    domains=["general"],
    complexity=QueryComplexity.SIMPLE,
    confidence=0.5,
    reasoning="error_occurred"
)
```

**Rationale**: Better to try tools than miss them

### Strategy 2: Structured Logging

Log all errors with context:

```python
logger.error(
    "intent_analysis_failed",
    error=str(e),
    error_type=type(e).__name__,
    query_preview=query[:50],
    model=self.config.model_routing,
    timestamp=datetime.now().isoformat()
)
```

**Rationale**: Enable debugging and monitoring

### Strategy 3: Error Counters

Track error types for monitoring:

```python
monitor.record_error("llm_api_failure")
monitor.record_error("json_parse_failure")
monitor.record_error("validation_failed")
```

**Rationale**: Identify patterns and trigger alerts

### Strategy 4: Graceful Degradation

Continue operation with reduced functionality:

```python
# If LLM fails, use fallback
# If cache fails, continue without cache
# If monitoring fails, continue without metrics
```

**Rationale**: Maximize availability

## Recovery Procedures

### Recovery 1: Retry with Backoff

```python
import asyncio

async def analyze_with_retry(query: str, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            return await analyzer.analyze(query)
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(
                    "retry_attempt",
                    attempt=attempt + 1,
                    wait_time=wait_time,
                    error=str(e)
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error("max_retries_exceeded", error=str(e))
                return analyzer._fallback_analysis("max_retries_exceeded")
```

### Recovery 2: Circuit Breaker

```python
class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open
    
    async def call(self, func, *args, **kwargs):
        if self.state == "open":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "half-open"
            else:
                raise Exception("Circuit breaker is open")
        
        try:
            result = await func(*args, **kwargs)
            if self.state == "half-open":
                self.state = "closed"
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                logger.error("circuit_breaker_opened")
            
            raise
```

### Recovery 3: Fallback Chain

```python
async def analyze_with_fallback_chain(query: str):
    # Try primary analyzer
    try:
        return await primary_analyzer.analyze(query)
    except Exception as e:
        logger.warning("primary_analyzer_failed", error=str(e))
    
    # Try secondary analyzer (different model)
    try:
        return await secondary_analyzer.analyze(query)
    except Exception as e:
        logger.warning("secondary_analyzer_failed", error=str(e))
    
    # Use safe default
    logger.error("all_analyzers_failed")
    return IntentAnalysis(
        intent=IntentType.TOOL_REQUIRED,
        domains=["general"],
        complexity=QueryComplexity.SIMPLE,
        confidence=0.5,
        reasoning="all_analyzers_failed"
    )
```

## Monitoring Errors

### Error Metrics

```python
monitor = get_intent_monitor()
metrics = monitor.get_metrics()

print(f"Failed queries: {metrics.failed_queries}")
print(f"Error rate: {metrics.error_rate:.1%}")
print(f"LLM API failures: {metrics.llm_api_failures}")
print(f"JSON parse failures: {metrics.json_parse_failures}")
```

### Error Alerts

```python
alerts = monitor.check_alerts()
for alert in alerts:
    if alert['alert_type'] == 'high_error_rate':
        send_alert(alert['message'], severity=alert['severity'])
```

## Best Practices

1. **Always log errors** with context for debugging
2. **Use safe defaults** that don't break the system
3. **Track error types** to identify patterns
4. **Implement retry logic** with exponential backoff
5. **Use circuit breakers** to prevent cascading failures
6. **Monitor error rates** and alert on thresholds
7. **Test error scenarios** in development
8. **Document fallback behavior** for users

## Testing Error Scenarios

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_llm_api_failure():
    """Test fallback when LLM API fails."""
    analyzer = UnifiedIntentAnalyzer(mock_llm_client, config)
    
    # Mock LLM to raise exception
    analyzer.llm_client.generate_response = AsyncMock(
        side_effect=Exception("API unavailable")
    )
    
    # Should return fallback
    analysis = await analyzer.analyze("Che tempo fa?")
    assert analysis.intent == IntentType.TOOL_REQUIRED
    assert analysis.domains == ["general"]
    assert analysis.confidence == 0.5

@pytest.mark.asyncio
async def test_json_parse_failure():
    """Test fallback when JSON parsing fails."""
    analyzer = UnifiedIntentAnalyzer(mock_llm_client, config)
    
    # Mock LLM to return invalid JSON
    mock_response = AsyncMock()
    mock_response.choices[0].message.content = "invalid json"
    analyzer.llm_client.generate_response = AsyncMock(return_value=mock_response)
    
    # Should return fallback
    analysis = await analyzer.analyze("Che tempo fa?")
    assert analysis.intent == IntentType.TOOL_REQUIRED
    assert analysis.confidence == 0.5

@pytest.mark.asyncio
async def test_empty_query():
    """Test handling of empty query."""
    analyzer = UnifiedIntentAnalyzer(mock_llm_client, config)
    
    # Should return conversational without LLM call
    analysis = await analyzer.analyze("")
    assert analysis.intent == IntentType.CONVERSATIONAL
    assert analysis.domains == []
    assert analysis.confidence == 1.0
```

## See Also

- [UnifiedIntentAnalyzer Guide](./unified-intent-analysis.md)
- [Monitoring Guide](./MONITORING.md)
- [API Reference](./api/unified-intent-analyzer.md)
