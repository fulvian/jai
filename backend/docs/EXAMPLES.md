# UnifiedIntentAnalyzer: Common Use Cases

## Example 1: Weather Query Classification

```python
from me4brain.engine.unified_intent_analyzer import UnifiedIntentAnalyzer, IntentType
from me4brain.llm.provider_factory import get_reasoning_client
from me4brain.llm.config import get_llm_config

async def classify_weather_query():
    llm_client = get_reasoning_client()
    config = get_llm_config()
    analyzer = UnifiedIntentAnalyzer(llm_client, config)
    
    # Italian weather query
    analysis = await analyzer.analyze("Che tempo fa a Roma?")
    print(f"Intent: {analysis.intent}")  # TOOL_REQUIRED
    print(f"Domains: {analysis.domains}")  # ["geo_weather"]
    print(f"Confidence: {analysis.confidence}")  # 0.95+
    
    # English weather query
    analysis = await analyzer.analyze("What's the weather in Milan?")
    print(f"Intent: {analysis.intent}")  # TOOL_REQUIRED
    print(f"Domains: {analysis.domains}")  # ["geo_weather"]
```

## Example 2: Conversational Query Classification

```python
async def classify_conversational_query():
    analyzer = UnifiedIntentAnalyzer(llm_client, config)
    
    # Greeting
    analysis = await analyzer.analyze("Ciao!")
    assert analysis.intent == IntentType.CONVERSATIONAL
    assert analysis.domains == []
    
    # Small talk
    analysis = await analyzer.analyze("Come stai?")
    assert analysis.intent == IntentType.CONVERSATIONAL
    assert analysis.domains == []
    
    # Meta question
    analysis = await analyzer.analyze("Chi sei?")
    assert analysis.intent == IntentType.CONVERSATIONAL
    assert analysis.domains == []
```

## Example 3: Multi-Domain Query

```python
async def classify_multi_domain_query():
    analyzer = UnifiedIntentAnalyzer(llm_client, config)
    
    query = "Che tempo fa a Roma e qual è il prezzo del Bitcoin?"
    analysis = await analyzer.analyze(query)
    
    print(f"Intent: {analysis.intent}")  # TOOL_REQUIRED
    print(f"Domains: {analysis.domains}")  # ["geo_weather", "finance_crypto"]
    print(f"Complexity: {analysis.complexity}")  # COMPLEX
    
    # Use domains to filter tools
    tools = await retriever.retrieve(query, domains=analysis.domains)
```

## Example 4: Confidence-Based Routing

```python
async def confidence_based_routing(query: str):
    analyzer = UnifiedIntentAnalyzer(llm_client, config)
    analysis = await analyzer.analyze(query)
    
    if analysis.confidence > 0.9:
        # High confidence - proceed directly
        if analysis.intent == IntentType.CONVERSATIONAL:
            response = await llm.generate_response(query)
        else:
            tools = await retriever.retrieve(query, analysis.domains)
            results = await executor.execute(tools)
            response = await synthesizer.synthesize(query, results)
    
    elif analysis.confidence > 0.7:
        # Medium confidence - proceed with caution
        if analysis.intent == IntentType.TOOL_REQUIRED:
            tools = await retriever.retrieve(query, analysis.domains, top_k=5)
            results = await executor.execute(tools)
            response = await synthesizer.synthesize(query, results)
        else:
            response = await llm.generate_response(query)
    
    else:
        # Low confidence - ask for clarification
        response = "I'm not sure what you need. Could you clarify?"
    
    return response
```

## Example 5: Complexity-Based Execution

```python
from me4brain.engine.unified_intent_analyzer import QueryComplexity

async def complexity_based_execution(query: str):
    analyzer = UnifiedIntentAnalyzer(llm_client, config)
    analysis = await analyzer.analyze(query)
    
    if analysis.complexity == QueryComplexity.SIMPLE:
        # Fast path: single tool, single domain
        tools = await retriever.retrieve(query, analysis.domains, top_k=5)
        results = await executor.execute(tools)
        response = await synthesizer.synthesize(query, results)
    
    elif analysis.complexity == QueryComplexity.MODERATE:
        # Standard path: multiple tools, single domain
        tools = await retriever.retrieve(query, analysis.domains, top_k=10)
        results = await executor.execute(tools)
        response = await synthesizer.synthesize(query, results)
    
    else:  # COMPLEX
        # Iterative path: multiple tools, multiple domains
        response = await engine.run_iterative(query)
    
    return response
```

## Example 6: Integration with ToolCallingEngine

```python
async def full_pipeline_example():
    # Create engine (analyzer is initialized automatically)
    engine = await ToolCallingEngine.create()
    
    # Weather query
    response = await engine.run("Che tempo fa a Roma?")
    print(response.answer)  # Weather information
    print(response.tools_called)  # ["openmeteo_weather"]
    
    # Conversational query
    response = await engine.run("Ciao, come stai?")
    print(response.answer)  # Conversational response
    print(response.tools_called)  # []
    
    # Multi-domain query
    response = await engine.run(
        "Che tempo fa a Roma e qual è il prezzo del Bitcoin?"
    )
    print(response.answer)  # Combined response
    print(response.tools_called)  # ["openmeteo_weather", "coingecko_price"]
```

## Example 7: Batch Processing

```python
async def batch_classification(queries: list[str]):
    analyzer = UnifiedIntentAnalyzer(llm_client, config)
    
    results = []
    for query in queries:
        analysis = await analyzer.analyze(query)
        results.append({
            "query": query,
            "intent": analysis.intent.value,
            "domains": analysis.domains,
            "confidence": analysis.confidence,
        })
    
    return results

# Usage
queries = [
    "Che tempo fa?",
    "Ciao",
    "Prezzo Bitcoin",
    "Come stai?",
]
results = await batch_classification(queries)
for result in results:
    print(f"{result['query']}: {result['intent']} ({result['confidence']:.2f})")
```

## Example 8: Error Handling

```python
async def robust_classification(query: str):
    analyzer = UnifiedIntentAnalyzer(llm_client, config)
    
    try:
        analysis = await analyzer.analyze(query)
        
        # Check for fallback (low confidence indicates error)
        if analysis.confidence < 0.5 and "failed" in analysis.reasoning:
            logger.warning(
                "classification_failed",
                query_preview=query[:50],
                reason=analysis.reasoning,
            )
            # Use safe default
            return await llm.generate_response(query)
        
        # Normal processing
        if analysis.intent == IntentType.CONVERSATIONAL:
            return await llm.generate_response(query)
        else:
            tools = await retriever.retrieve(query, analysis.domains)
            results = await executor.execute(tools)
            return await synthesizer.synthesize(query, results)
    
    except Exception as e:
        logger.error("classification_error", error=str(e))
        # Fallback to safe default
        return await llm.generate_response(query)
```

## Example 9: Monitoring and Metrics

```python
import time
from collections import defaultdict

async def monitored_classification(query: str):
    analyzer = UnifiedIntentAnalyzer(llm_client, config)
    
    start_time = time.monotonic()
    analysis = await analyzer.analyze(query)
    latency_ms = (time.monotonic() - start_time) * 1000
    
    # Log metrics
    logger.info(
        "intent_analyzed",
        query_preview=query[:50],
        intent=analysis.intent.value,
        domains=analysis.domains,
        complexity=analysis.complexity.value,
        confidence=analysis.confidence,
        latency_ms=round(latency_ms, 2),
    )
    
    # Track statistics
    stats = {
        "total_queries": 0,
        "conversational": 0,
        "tool_required": 0,
        "avg_latency_ms": 0,
        "avg_confidence": 0,
    }
    
    stats["total_queries"] += 1
    if analysis.intent == IntentType.CONVERSATIONAL:
        stats["conversational"] += 1
    else:
        stats["tool_required"] += 1
    
    return analysis, stats
```

## Example 10: Custom Domain Handling

```python
async def handle_custom_domain(query: str):
    analyzer = UnifiedIntentAnalyzer(llm_client, config)
    analysis = await analyzer.analyze(query)
    
    # Map domains to custom handlers
    domain_handlers = {
        "geo_weather": handle_weather,
        "finance_crypto": handle_finance,
        "web_search": handle_search,
        "communication": handle_communication,
        "scheduling": handle_scheduling,
    }
    
    if analysis.intent == IntentType.CONVERSATIONAL:
        return await llm.generate_response(query)
    
    # Execute handlers for each domain
    results = []
    for domain in analysis.domains:
        handler = domain_handlers.get(domain)
        if handler:
            result = await handler(query)
            results.append(result)
    
    # Synthesize results
    return await synthesizer.synthesize(query, results)
```

## Example 11: Caching Strategy

```python
from functools import lru_cache

class CachedAnalyzer:
    def __init__(self, analyzer: UnifiedIntentAnalyzer):
        self.analyzer = analyzer
        self.cache = {}
    
    async def analyze(self, query: str, context: str | None = None):
        # Create cache key
        cache_key = (query, context)
        
        # Check cache
        if cache_key in self.cache:
            logger.info("cache_hit", query_preview=query[:50])
            return self.cache[cache_key]
        
        # Analyze
        analysis = await self.analyzer.analyze(query, context)
        
        # Store in cache
        self.cache[cache_key] = analysis
        logger.info("cache_miss", query_preview=query[:50])
        
        return analysis

# Usage
cached_analyzer = CachedAnalyzer(analyzer)
analysis1 = await cached_analyzer.analyze("Che tempo fa?")  # LLM call
analysis2 = await cached_analyzer.analyze("Che tempo fa?")  # Cache hit
```

## Example 12: A/B Testing

```python
async def ab_test_classification(query: str):
    analyzer_v1 = UnifiedIntentAnalyzer(llm_client, config_v1)
    analyzer_v2 = UnifiedIntentAnalyzer(llm_client, config_v2)
    
    # Analyze with both versions
    analysis_v1 = await analyzer_v1.analyze(query)
    analysis_v2 = await analyzer_v2.analyze(query)
    
    # Compare results
    if analysis_v1.intent != analysis_v2.intent:
        logger.warning(
            "ab_test_mismatch",
            query_preview=query[:50],
            v1_intent=analysis_v1.intent.value,
            v2_intent=analysis_v2.intent.value,
            v1_confidence=analysis_v1.confidence,
            v2_confidence=analysis_v2.confidence,
        )
    
    # Use v2 if more confident
    if analysis_v2.confidence > analysis_v1.confidence:
        return analysis_v2
    else:
        return analysis_v1
```

## See Also

- [UnifiedIntentAnalyzer Guide](./unified-intent-analysis.md)
- [API Reference](./api/unified-intent-analyzer.md)
- [Migration Guide](./MIGRATION_GUIDE.md)
