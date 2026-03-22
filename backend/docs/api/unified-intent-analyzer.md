# UnifiedIntentAnalyzer API Reference

## Module: `me4brain.engine.unified_intent_analyzer`

### Classes

#### IntentType

```python
class IntentType(str, Enum):
    """Query intent classification."""
    
    CONVERSATIONAL = "conversational"
    TOOL_REQUIRED = "tool_required"
```

#### QueryComplexity

```python
class QueryComplexity(str, Enum):
    """Query complexity level."""
    
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
```

#### IntentAnalysis

```python
@dataclass
class IntentAnalysis:
    """Result of unified intent analysis.
    
    Attributes:
        intent: Intent type (conversational or tool_required)
        domains: List of relevant domains (empty for conversational)
        complexity: Query complexity (simple, moderate, complex)
        confidence: Confidence score (0.0 to 1.0)
        reasoning: LLM explanation for the classification
    """
    
    intent: IntentType
    domains: list[str]
    complexity: QueryComplexity
    confidence: float
    reasoning: str
    
    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "intent": self.intent.value,
            "domains": self.domains,
            "complexity": self.complexity.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }
```

#### UnifiedIntentAnalyzer

```python
class UnifiedIntentAnalyzer:
    """Unified intent analyzer using LLM-based classification.
    
    Replaces ConversationalDetector with a scalable, LLM-based approach that:
    - Classifies queries as conversational or tool-required
    - Identifies relevant domains for tool-required queries
    - Assesses query complexity
    - Provides confidence scores
    - Handles errors gracefully with fallback behavior
    """
    
    def __init__(
        self,
        llm_client: LLMProvider,
        config: Any,
    ) -> None:
        """Initialize the analyzer.
        
        Args:
            llm_client: LLM client for classification
            config: Configuration object with model settings
        """
    
    async def analyze(
        self,
        query: str,
        context: str | None = None,
    ) -> IntentAnalysis:
        """Analyze query intent using LLM.
        
        Args:
            query: User query to analyze
            context: Optional additional context
        
        Returns:
            IntentAnalysis with intent type, domains, and complexity
        
        Raises:
            ValueError: If query is invalid
        
        Example:
            >>> analyzer = UnifiedIntentAnalyzer(llm_client, config)
            >>> analysis = await analyzer.analyze("Che tempo fa?")
            >>> print(analysis.intent)
            IntentType.TOOL_REQUIRED
        """
```

### Methods

#### analyze()

**Signature:**
```python
async def analyze(
    self,
    query: str,
    context: str | None = None,
) -> IntentAnalysis
```

**Parameters:**
- `query` (str): User query to analyze (required)
- `context` (str | None): Optional additional context

**Returns:**
- `IntentAnalysis`: Classification result with intent, domains, complexity, confidence, and reasoning

**Raises:**
- `ValueError`: If query is empty or invalid

**Example:**
```python
analysis = await analyzer.analyze("Che tempo fa a Roma?")
assert analysis.intent == IntentType.TOOL_REQUIRED
assert "geo_weather" in analysis.domains
assert analysis.confidence > 0.8
```

**Error Handling:**
- If LLM API fails: Returns fallback with `intent=TOOL_REQUIRED`, `domains=["general"]`, `confidence=0.5`
- If JSON parsing fails: Returns fallback with same defaults
- If empty query: Returns `intent=CONVERSATIONAL`, `domains=[]`, `confidence=1.0`

### Constants

#### AVAILABLE_DOMAINS

```python
AVAILABLE_DOMAINS = [
    "geo_weather",
    "finance_crypto",
    "web_search",
    "communication",
    "scheduling",
    "file_management",
    "data_analysis",
    "travel",
    "food",
    "entertainment",
    "sports",
    "shopping",
]
```

#### WEATHER_KEYWORDS

```python
WEATHER_KEYWORDS = [
    "tempo", "meteo", "previsioni", "temperatura", "clima",
    "weather", "forecast", "temperature", "climate",
]
```

#### PRICE_KEYWORDS

```python
PRICE_KEYWORDS = [
    "prezzo", "price", "cost", "costo",
]
```

#### SEARCH_KEYWORDS

```python
SEARCH_KEYWORDS = [
    "cerca", "search", "trova", "find", "notizie", "news",
]
```

### Usage Examples

#### Example 1: Weather Query

```python
analyzer = UnifiedIntentAnalyzer(llm_client, config)
analysis = await analyzer.analyze("Che tempo fa a Caltanissetta?")

assert analysis.intent == IntentType.TOOL_REQUIRED
assert analysis.domains == ["geo_weather"]
assert analysis.complexity == QueryComplexity.SIMPLE
assert analysis.confidence > 0.8
```

#### Example 2: Conversational Query

```python
analysis = await analyzer.analyze("Ciao, come stai?")

assert analysis.intent == IntentType.CONVERSATIONAL
assert analysis.domains == []
assert analysis.complexity == QueryComplexity.SIMPLE
assert analysis.confidence > 0.9
```

#### Example 3: Multi-Domain Query

```python
analysis = await analyzer.analyze(
    "Che tempo fa a Roma e qual è il prezzo del Bitcoin?"
)

assert analysis.intent == IntentType.TOOL_REQUIRED
assert set(analysis.domains) == {"geo_weather", "finance_crypto"}
assert analysis.complexity == QueryComplexity.COMPLEX
```

#### Example 4: With Context

```python
context = "L'utente sta pianificando un viaggio a Roma"
analysis = await analyzer.analyze(
    "Che tempo fa?",
    context=context
)

# Context helps with disambiguation
assert analysis.intent == IntentType.TOOL_REQUIRED
assert analysis.domains == ["geo_weather"]
```

#### Example 5: Confidence-Based Routing

```python
analysis = await analyzer.analyze(query)

if analysis.confidence > 0.9:
    # High confidence - proceed directly
    if analysis.intent == IntentType.CONVERSATIONAL:
        response = await llm.generate_response(query)
    else:
        tools = await retriever.retrieve(query, analysis.domains)
elif analysis.confidence > 0.7:
    # Medium confidence - proceed with caution
    tools = await retriever.retrieve(query, analysis.domains, top_k=5)
else:
    # Low confidence - ask for clarification
    response = "I'm not sure. Could you clarify?"
```

#### Example 6: Complexity-Based Execution

```python
analysis = await analyzer.analyze(query)

if analysis.complexity == QueryComplexity.SIMPLE:
    # Fast path
    tools = await retriever.retrieve(query, analysis.domains, top_k=5)
    results = await executor.execute(tools)
elif analysis.complexity == QueryComplexity.MODERATE:
    # Standard path
    tools = await retriever.retrieve(query, analysis.domains, top_k=10)
    results = await executor.execute(tools)
else:  # COMPLEX
    # Iterative path
    results = await engine.run_iterative(query)
```

### Error Handling

#### Fallback Behavior

When classification fails, the analyzer returns a safe default:

```python
IntentAnalysis(
    intent=IntentType.TOOL_REQUIRED,
    domains=["general"],
    complexity=QueryComplexity.SIMPLE,
    confidence=0.5,
    reasoning="llm_api_failed"
)
```

#### Error Scenarios

| Scenario | Handling | Reasoning |
|----------|----------|-----------|
| LLM API unavailable | Fallback | "llm_api_failed" |
| Invalid JSON response | Fallback | "json_parse_failed" |
| Empty query | Conversational | "empty_query" |
| Invalid domain | Filter | "invalid_domain_filtered" |

### Logging

All operations are logged with structured data:

```python
# Example log output
{
    "event": "intent_analyzed",
    "query_preview": "Che tempo fa?",
    "intent": "tool_required",
    "domains": ["geo_weather"],
    "complexity": "simple",
    "confidence": 0.95,
    "latency_ms": 125
}
```

### Performance

| Metric | Value |
|--------|-------|
| Latency (p95) | 150ms |
| Latency (p99) | 200ms |
| Throughput | 100 queries/sec |
| Cache hit rate | 20-40% |

### Configuration

```python
# Environment variables
INTENT_ANALYSIS_MODEL=mistral-large-3
INTENT_CACHE_TTL=300
INTENT_ANALYSIS_TIMEOUT=5
USE_UNIFIED_INTENT_ANALYZER=true

# Programmatic
config = get_llm_config()
config.intent_analysis_timeout = 5
config.intent_cache_ttl = 300
config.intent_analysis_model = "mistral-large-3"
```

### See Also

- [UnifiedIntentAnalyzer Guide](../unified-intent-analysis.md)
- [Migration Guide](../MIGRATION_GUIDE.md)
- [ToolCallingEngine API](./tool-calling-engine.md)
