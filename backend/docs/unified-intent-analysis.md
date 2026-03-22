# UnifiedIntentAnalyzer: Comprehensive Guide

## Overview

The `UnifiedIntentAnalyzer` is the core component for intelligent query classification in Me4BrAIn. It replaces the old regex-based `ConversationalDetector` with an LLM-powered system that:

- **Classifies intent** (conversational vs. tool-required)
- **Identifies domains** (weather, finance, search, etc.)
- **Assesses complexity** (simple, moderate, complex)
- **Provides confidence scores** for classification certainty
- **Handles errors gracefully** with fallback behavior

## Quick Start

### Basic Usage

```python
from me4brain.engine.unified_intent_analyzer import UnifiedIntentAnalyzer, IntentType
from me4brain.llm.provider_factory import get_reasoning_client
from me4brain.llm.config import get_llm_config

# Initialize
llm_client = get_reasoning_client()
config = get_llm_config()
analyzer = UnifiedIntentAnalyzer(llm_client, config)

# Analyze a query
analysis = await analyzer.analyze("Che tempo fa a Roma?")

# Access results
print(f"Intent: {analysis.intent}")  # IntentType.TOOL_REQUIRED
print(f"Domains: {analysis.domains}")  # ["geo_weather"]
print(f"Complexity: {analysis.complexity}")  # QueryComplexity.SIMPLE
print(f"Confidence: {analysis.confidence}")  # 0.95
print(f"Reasoning: {analysis.reasoning}")  # "Weather query detected"
```

### With ToolCallingEngine

The analyzer is automatically integrated:

```python
engine = await ToolCallingEngine.create()
response = await engine.run("Che tempo fa a Roma?")
# Intent analysis happens automatically
```

## Data Models

### IntentType

```python
class IntentType(str, Enum):
    CONVERSATIONAL = "conversational"  # Greetings, small talk, meta questions
    TOOL_REQUIRED = "tool_required"    # Requires API calls, data retrieval
```

### QueryComplexity

```python
class QueryComplexity(str, Enum):
    SIMPLE = "simple"        # Single tool, single domain
    MODERATE = "moderate"    # Multiple tools, single domain
    COMPLEX = "complex"      # Multiple tools, multiple domains
```

### IntentAnalysis

```python
@dataclass
class IntentAnalysis:
    intent: IntentType              # conversational | tool_required
    domains: list[str]              # Relevant domains (empty for conversational)
    complexity: QueryComplexity      # simple | moderate | complex
    confidence: float               # 0.0 to 1.0
    reasoning: str                  # LLM explanation
```

## Available Domains

The analyzer supports these domains:

- **geo_weather**: Weather, forecasts, temperature, climate
- **finance_crypto**: Cryptocurrency prices, stocks, markets
- **web_search**: Web search, news, articles
- **communication**: Email, messaging, notifications
- **scheduling**: Calendar, events, reminders
- **file_management**: Documents, files, storage
- **data_analysis**: Data processing, analysis, visualization
- **travel**: Flights, hotels, transportation
- **food**: Restaurants, recipes, food delivery
- **entertainment**: Movies, music, events
- **sports**: Sports scores, schedules, news
- **shopping**: E-commerce, products, prices

## Classification Rules

### Conversational Queries

Classified as `CONVERSATIONAL` when:
- Greeting: "ciao", "hello", "buongiorno"
- Farewell: "arrivederci", "bye", "grazie"
- Small talk: "come stai?", "how are you?"
- Meta questions: "chi sei?", "what are you?"
- Opinions: "cosa pensi di X?"

### Tool-Required Queries

Classified as `TOOL_REQUIRED` when:
- **Weather**: Contains keywords like "tempo", "meteo", "weather", "forecast"
- **Prices**: Contains keywords like "prezzo", "price", "cost"
- **Search**: Contains keywords like "cerca", "search", "notizie", "news"
- **Other domains**: Matches any available domain

### Multi-Domain Queries

Queries can match multiple domains:

```python
# Example: "Che tempo fa a Roma e qual è il prezzo del Bitcoin?"
analysis = await analyzer.analyze(query)
# analysis.domains = ["geo_weather", "finance_crypto"]
# analysis.complexity = QueryComplexity.COMPLEX
```

## Usage Patterns

### Pattern 1: Simple Intent Check

```python
analysis = await analyzer.analyze(query)

if analysis.intent == IntentType.CONVERSATIONAL:
    # Generate direct response
    response = await llm.generate_response(query)
else:
    # Retrieve and execute tools
    tools = await retriever.retrieve(query, analysis.domains)
    results = await executor.execute(tools)
    response = await synthesizer.synthesize(query, results)
```

### Pattern 2: Domain-Filtered Tool Retrieval

```python
analysis = await analyzer.analyze(query)

if analysis.intent == IntentType.TOOL_REQUIRED:
    # Use domains to filter tools efficiently
    tools = await retriever.retrieve(
        query,
        domains=analysis.domains,
        top_k=10
    )
```

### Pattern 3: Confidence-Based Routing

```python
analysis = await analyzer.analyze(query)

if analysis.confidence > 0.9:
    # High confidence - proceed directly
    if analysis.intent == IntentType.CONVERSATIONAL:
        return await llm.generate_response(query)
    else:
        tools = await retriever.retrieve(query, analysis.domains)
elif analysis.confidence > 0.7:
    # Medium confidence - proceed with caution
    tools = await retriever.retrieve(query, analysis.domains, top_k=5)
else:
    # Low confidence - ask for clarification
    return "I'm not sure. Could you clarify what you need?"
```

### Pattern 4: Complexity-Based Execution

```python
analysis = await analyzer.analyze(query)

if analysis.complexity == QueryComplexity.SIMPLE:
    # Fast path: single tool
    tools = await retriever.retrieve(query, analysis.domains, top_k=5)
    results = await executor.execute(tools)
elif analysis.complexity == QueryComplexity.MODERATE:
    # Standard path: multiple tools
    tools = await retriever.retrieve(query, analysis.domains, top_k=10)
    results = await executor.execute(tools)
else:  # COMPLEX
    # Iterative path: decompose and execute step-by-step
    return await engine.run_iterative(query)
```

## Error Handling

### Fallback Behavior

If LLM classification fails, the analyzer returns a safe default:

```python
# Fallback: assume tool_required for safety
IntentAnalysis(
    intent=IntentType.TOOL_REQUIRED,
    domains=["general"],
    complexity=QueryComplexity.SIMPLE,
    confidence=0.5,
    reasoning="llm_api_failed"
)
```

### Error Scenarios

| Scenario | Handling |
|----------|----------|
| LLM API unavailable | Fallback to tool_required |
| Invalid JSON response | Fallback to tool_required |
| Empty query | Return conversational |
| Invalid domain in response | Filter out invalid domains |

## Performance Characteristics

### Latency

- **Conversational queries**: ~100-150ms (LLM call)
- **Tool-required queries**: ~100-150ms (LLM call)
- **Cached queries**: ~1-5ms (in-memory cache)

### Throughput

- **Single query**: ~100-150ms
- **Batch (10 queries)**: ~1-2 seconds
- **Concurrent (100 queries)**: ~2-3 seconds

### Accuracy

- **Weather queries**: 95%+
- **Conversational queries**: 98%+
- **Multi-domain queries**: 90%+
- **Overall**: 95%+

## Configuration

### Environment Variables

```bash
# Model for intent classification
INTENT_ANALYSIS_MODEL=mistral-large-3

# Cache TTL (seconds)
INTENT_CACHE_TTL=300

# Timeout (seconds)
INTENT_ANALYSIS_TIMEOUT=5

# Enable/disable intent analysis
USE_UNIFIED_INTENT_ANALYZER=true
```

### Programmatic Configuration

```python
from me4brain.llm.config import get_llm_config

config = get_llm_config()
config.intent_analysis_timeout = 5  # seconds
config.intent_cache_ttl = 300  # seconds
config.intent_analysis_model = "mistral-large-3"
```

## Monitoring and Observability

### Structured Logging

All operations are logged with structured data:

```python
# Example log output
{
    "event": "intent_analyzed",
    "query_preview": "Che tempo fa a Roma?",
    "intent": "tool_required",
    "domains": ["geo_weather"],
    "complexity": "simple",
    "confidence": 0.95,
    "latency_ms": 125
}
```

### Metrics

Track these metrics in production:

- **Classification latency**: 95th percentile < 200ms
- **Accuracy**: 95%+ for weather, 98%+ for conversational
- **Error rate**: < 1%
- **Cache hit rate**: 20-40% (depends on query patterns)

### Alerts

Set up alerts for:

- High error rate (> 5%)
- High latency (95th percentile > 300ms)
- Low confidence (< 0.7) for > 10% of queries
- LLM API failures

## Advanced Topics

### Custom Domain Addition

To add a new domain:

1. Update the prompt in `_build_intent_prompt()`
2. Add domain to `AVAILABLE_DOMAINS` list
3. Update tool retriever to recognize new domain
4. Test with property-based tests

### Confidence Calibration

Adjust confidence thresholds based on your use case:

```python
# Conservative: only proceed if very confident
if analysis.confidence > 0.95:
    proceed()

# Balanced: proceed if reasonably confident
if analysis.confidence > 0.8:
    proceed()

# Aggressive: proceed even with low confidence
if analysis.confidence > 0.6:
    proceed()
```

### Caching Strategy

The analyzer supports session-based caching:

```python
# Same query in same session uses cache
analysis1 = await analyzer.analyze("Che tempo fa?")  # LLM call
analysis2 = await analyzer.analyze("Che tempo fa?")  # Cache hit
```

## Troubleshooting

### Issue: "Query misclassified"

**Diagnosis:**
1. Check confidence score
2. Review reasoning field
3. Check LLM model being used

**Solution:**
1. If confidence < 0.8, implement confidence-based routing
2. Provide user feedback to improve model
3. Consider using different LLM model

### Issue: "Performance degradation"

**Diagnosis:**
1. Check latency metrics
2. Verify LLM API is responsive
3. Check cache hit rate

**Solution:**
1. Enable caching for identical queries
2. Use faster LLM model
3. Implement batch processing

### Issue: "Domain not recognized"

**Diagnosis:**
1. Check available domains list
2. Review LLM response

**Solution:**
1. Add domain to prompt if missing
2. Update tool retriever configuration
3. Test with property-based tests

## See Also

- [Migration Guide](./MIGRATION_GUIDE.md)
- [ToolCallingEngine Documentation](./api/tool-calling-engine.md)
- [Performance Benchmarks](./PERFORMANCE.md)
- [API Reference](./api/unified-intent-analyzer.md)
