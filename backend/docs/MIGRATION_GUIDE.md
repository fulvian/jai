# Migration Guide: ConversationalDetector → UnifiedIntentAnalyzer

## Overview

The `ConversationalDetector` has been **deprecated and removed** as of v0.15.0. It has been replaced by the `UnifiedIntentAnalyzer`, which provides:

- **LLM-based classification** instead of hardcoded regex patterns
- **Scalable domain support** without code changes
- **Better accuracy** for weather, prices, and multi-domain queries
- **Structured logging** for observability
- **Confidence scores** for classification certainty

## What Changed

### Before (Deprecated)

```python
# OLD: Hardcoded regex patterns
detector = ConversationalDetector()
is_conversational = detector.is_conversational("Che tempo fa?")  # ❌ Misclassified as conversational
```

### After (Current)

```python
# NEW: LLM-based classification
from me4brain.engine.unified_intent_analyzer import UnifiedIntentAnalyzer
from me4brain.llm.provider_factory import get_reasoning_client
from me4brain.llm.config import get_llm_config

llm_client = get_reasoning_client()
config = get_llm_config()
analyzer = UnifiedIntentAnalyzer(llm_client, config)

analysis = await analyzer.analyze("Che tempo fa?")
# Returns: IntentAnalysis(
#   intent=IntentType.TOOL_REQUIRED,
#   domains=["geo_weather"],
#   complexity=QueryComplexity.SIMPLE,
#   confidence=0.95,
#   reasoning="Weather query detected"
# )
```

## Migration Steps

### Step 1: Update Imports

**Before:**
```python
from me4brain.engine.conversational_detector import ConversationalDetector
```

**After:**
```python
from me4brain.engine.unified_intent_analyzer import UnifiedIntentAnalyzer, IntentType
```

### Step 2: Update Initialization

**Before:**
```python
detector = ConversationalDetector()
```

**After:**
```python
from me4brain.llm.provider_factory import get_reasoning_client
from me4brain.llm.config import get_llm_config

llm_client = get_reasoning_client()
config = get_llm_config()
analyzer = UnifiedIntentAnalyzer(llm_client, config)
```

### Step 3: Update Usage

**Before:**
```python
is_conversational = detector.is_conversational(query)
if is_conversational:
    # Handle conversational query
    response = await llm.generate_response(query)
else:
    # Handle tool-required query
    tools = await retriever.retrieve(query)
```

**After:**
```python
analysis = await analyzer.analyze(query)
if analysis.intent == IntentType.CONVERSATIONAL:
    # Handle conversational query
    response = await llm.generate_response(query)
else:
    # Handle tool-required query
    tools = await retriever.retrieve(query, analysis.domains)
```

### Step 4: Use Domains for Tool Retrieval

The new analyzer provides **domains** for better tool filtering:

```python
analysis = await analyzer.analyze("Che tempo fa a Roma e qual è il prezzo del Bitcoin?")

# analysis.domains = ["geo_weather", "finance_crypto"]
# Use domains to filter tools more efficiently
tools = await retriever.retrieve(query, domains=analysis.domains)
```

## Feature Comparison

| Feature | ConversationalDetector | UnifiedIntentAnalyzer |
|---------|----------------------|----------------------|
| Classification Method | Regex patterns | LLM-based |
| Weather Query Accuracy | 60% (misclassified) | 95%+ |
| Conversational Accuracy | 98% | 98%+ |
| Domain Support | Hardcoded (5 domains) | Scalable (50+ domains) |
| Confidence Score | ❌ No | ✅ Yes (0.0-1.0) |
| Complexity Assessment | ❌ No | ✅ Yes (simple/moderate/complex) |
| Multi-Domain Queries | ❌ Limited | ✅ Full support |
| Structured Logging | ❌ No | ✅ Yes |
| Error Handling | Basic | Comprehensive with fallback |
| Performance | ~50ms | ~100-150ms |

## Common Patterns

### Pattern 1: Simple Conversational Check

**Before:**
```python
if detector.is_conversational(query):
    return await llm.generate_response(query)
```

**After:**
```python
analysis = await analyzer.analyze(query)
if analysis.intent == IntentType.CONVERSATIONAL:
    return await llm.generate_response(query)
```

### Pattern 2: Tool Routing with Domains

**Before:**
```python
if not detector.is_conversational(query):
    tools = await retriever.retrieve(query)  # All tools
```

**After:**
```python
analysis = await analyzer.analyze(query)
if analysis.intent == IntentType.TOOL_REQUIRED:
    tools = await retriever.retrieve(query, domains=analysis.domains)  # Filtered by domain
```

### Pattern 3: Confidence-Based Routing

**New capability** - Route based on confidence:

```python
analysis = await analyzer.analyze(query)

if analysis.confidence > 0.9:
    # High confidence - proceed directly
    if analysis.intent == IntentType.CONVERSATIONAL:
        return await llm.generate_response(query)
    else:
        tools = await retriever.retrieve(query, analysis.domains)
else:
    # Low confidence - ask user for clarification
    return "I'm not sure if you want to use tools. Could you clarify?"
```

### Pattern 4: Complexity-Based Execution

**New capability** - Adjust execution strategy based on complexity:

```python
analysis = await analyzer.analyze(query)

if analysis.complexity == QueryComplexity.SIMPLE:
    # Fast path: single tool
    tools = await retriever.retrieve(query, analysis.domains, top_k=5)
elif analysis.complexity == QueryComplexity.MODERATE:
    # Standard path: multiple tools, single domain
    tools = await retriever.retrieve(query, analysis.domains, top_k=10)
else:  # COMPLEX
    # Iterative path: multiple tools, multiple domains
    return await engine.run_iterative(query)
```

## Integration with ToolCallingEngine

The `ToolCallingEngine` now uses `UnifiedIntentAnalyzer` automatically:

```python
# No changes needed - analyzer is initialized internally
engine = await ToolCallingEngine.create()

# Intent analysis happens automatically in run()
response = await engine.run("Che tempo fa a Roma?")
# Internally:
# 1. Analyzes intent → tool_required + geo_weather
# 2. Retrieves weather tools
# 3. Executes tools
# 4. Synthesizes response
```

## Deprecation Timeline

| Version | Status | Action |
|---------|--------|--------|
| v0.14.x | Active | ConversationalDetector available |
| v0.15.0 | **Deprecated** | ConversationalDetector removed, UnifiedIntentAnalyzer required |
| v0.16.0+ | Removed | No backward compatibility |

## Troubleshooting

### Issue: "Query misclassified as conversational"

**Cause:** LLM may have different interpretation than regex patterns

**Solution:** 
1. Check the confidence score: `analysis.confidence`
2. If low confidence, implement confidence-based routing
3. Provide feedback to improve the model

### Issue: "Performance degradation"

**Cause:** LLM call adds ~50-100ms latency

**Solution:**
1. Enable caching for identical queries
2. Use faster model for intent classification
3. Implement batch processing for multiple queries

### Issue: "Domain not recognized"

**Cause:** Domain not in available domains list

**Solution:**
1. Check available domains in the prompt
2. Add new domain to config if needed
3. Update prompt to include new domain

## Support

For issues or questions:
1. Check the [UnifiedIntentAnalyzer documentation](./unified-intent-analysis.md)
2. Review [API documentation](./api/unified-intent-analyzer.md)
3. Check [troubleshooting guide](./TROUBLESHOOTING.md)

## See Also

- [UnifiedIntentAnalyzer Documentation](./unified-intent-analysis.md)
- [ToolCallingEngine Integration](./api/tool-calling-engine.md)
- [Performance Benchmarks](./PERFORMANCE.md)
