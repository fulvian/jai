# Conversational Detector Weather Fix - Bugfix Design

## Overview

Weather queries in Italian and English (e.g., "Che tempo fa a Caltanissetta?", "weather in Rome") are incorrectly classified as conversational by the ConversationalDetector, causing the system to bypass tool routing and return generic responses instead of fetching real weather data. This fix adds weather-specific keywords to the fast-path regex patterns and improves the LLM prompt to explicitly recognize weather queries as tool-requiring. The fix is minimal and targeted: it adds a single regex pattern and enhances the LLM prompt with explicit weather examples, ensuring existing conversational detection remains unchanged.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug - when weather queries are incorrectly classified as conversational
- **Property (P)**: The desired behavior when weather queries are submitted - they should be classified as tool-requiring and routed to weather tools
- **Preservation**: Existing conversational detection for greetings, farewells, small talk, and meta questions must remain unchanged
- **ConversationalDetector**: The class in `src/me4brain/engine/conversational_detector.py` that determines if a query is pure conversation or requires tools
- **Fast-path**: Regex pattern matching that runs in < 1ms to quickly identify conversational queries
- **Slow-path**: LLM-based classification that runs in ~50-100ms for ambiguous queries
- **CONVERSATIONAL_PATTERNS**: Dictionary of regex patterns used in fast-path detection

## Bug Details

### Bug Condition

The bug manifests when a user submits a weather query in Italian or English. The ConversationalDetector either fails to match weather keywords in the fast-path regex patterns (because no weather pattern exists), or the LLM slow-path misclassifies the query as conversational due to ambiguous prompt guidance.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type str (user query)
  OUTPUT: boolean
  
  RETURN containsWeatherKeywords(input)
         AND NOT matchedByFastPath(input, "weather")
         AND classifiedAsConversational(input)
END FUNCTION

FUNCTION containsWeatherKeywords(query)
  weather_keywords = [
    "tempo", "meteo", "previsioni", "temperatura", "clima",
    "weather", "forecast", "temperature", "climate"
  ]
  RETURN ANY keyword IN weather_keywords WHERE keyword IN query.lower()
END FUNCTION
```

### Examples

- **Italian weather query**: "Che tempo fa a Caltanissetta?" → Currently classified as conversational (WRONG) → Should be classified as tool-requiring and route to openmeteo_weather
- **Short Italian weather**: "meteo a Roma" → Currently classified as conversational (WRONG) → Should be classified as tool-requiring
- **English weather query**: "weather in Milan" → Currently classified as conversational (WRONG) → Should be classified as tool-requiring
- **Temperature query**: "temperatura Napoli" → Currently classified as conversational (WRONG) → Should be classified as tool-requiring
- **Edge case - ambiguous**: "come va il tempo?" (how's the weather/how's it going) → Should be classified as tool-requiring if context suggests weather

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Greeting patterns ("ciao", "hello", "buongiorno") must continue to be classified as conversational
- Farewell patterns ("arrivederci", "grazie", "bye") must continue to be classified as conversational
- Small talk patterns ("come stai", "how are you") must continue to be classified as conversational
- Meta questions about the bot ("chi sei", "cosa puoi fare") must continue to be classified as conversational
- Opinion requests ("cosa pensi", "secondo te") must continue to be classified as conversational
- Joke requests ("raccontami una barzelletta") must continue to be classified as conversational
- Non-weather tool queries ("prezzo bitcoin", "terremoti recenti", "cerca notizie") must continue to be classified as tool-requiring

**Scope:**
All inputs that do NOT involve weather keywords should be completely unaffected by this fix. This includes:
- All existing conversational patterns (greetings, farewells, small talk, meta questions, opinions, jokes)
- All other tool-requiring queries (prices, earthquakes, news, email, etc.)
- The fast-path and slow-path detection logic flow

## Hypothesized Root Cause

Based on the bug description and code analysis, the root causes are:

1. **Missing Weather Pattern in Fast-Path**: The `CONVERSATIONAL_PATTERNS` dictionary does not include a "weather" pattern, so weather queries never match in the fast-path and fall through to the slow-path LLM classification.

2. **Ambiguous LLM Prompt**: The slow-path LLM prompt includes examples of short queries that require tools ("che tempo fa a Roma?", "prezzo bitcoin oggi"), but these are buried in the prompt and may not be weighted heavily enough by the LLM. The prompt emphasizes that "length doesn't matter" but doesn't explicitly list weather as a tool-requiring category.

3. **Pattern Matching Order**: Weather queries don't match any existing conversational patterns, so they correctly fall through to the slow-path, but the LLM then misclassifies them.

4. **Language Coverage**: The current patterns are primarily Italian-focused, but weather queries can come in multiple languages (Italian, English), requiring language-agnostic keyword matching.

## Correctness Properties

Property 1: Bug Condition - Weather Queries Require Tools

_For any_ input query that contains weather-related keywords (tempo, meteo, previsioni, temperatura, clima, weather, forecast, temperature, climate), the fixed ConversationalDetector SHALL classify it as tool-requiring (is_conversational=False), enabling the system to route the query to the geo_weather domain and call the openmeteo_weather tool.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Non-Weather Conversational Detection

_For any_ input query that does NOT contain weather keywords and matches existing conversational patterns (greetings, farewells, small talk, meta questions, opinions, jokes), the fixed ConversationalDetector SHALL produce exactly the same classification as the original code, preserving all existing conversational detection behavior.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `src/me4brain/engine/conversational_detector.py`

**Class**: `ConversationalDetector`

**Specific Changes**:

1. **Add Weather Pattern to Fast-Path**: Add a new "weather" entry to the `CONVERSATIONAL_PATTERNS` dictionary that matches common weather keywords in Italian and English.
   - Pattern should match queries containing: tempo, meteo, previsioni, temperatura, clima, weather, forecast, temperature, climate
   - Pattern should be case-insensitive and Unicode-aware
   - Pattern should NOT match at start of string (unlike greetings) since weather queries can have various structures
   - Suggested regex: `r"(tempo|meteo|previsioni|temperatura|clima|weather|forecast|temperature|climate)"`

2. **Invert Logic for Weather Pattern**: Unlike other patterns in `CONVERSATIONAL_PATTERNS` which return `True` (is conversational), the weather pattern should return `False` (is NOT conversational, requires tools). This requires modifying the fast-path logic to handle "anti-patterns" that explicitly mark queries as tool-requiring.

3. **Alternative Approach - Separate Tool-Required Patterns**: Instead of inverting logic, create a separate `TOOL_REQUIRED_PATTERNS` dictionary that is checked BEFORE `CONVERSATIONAL_PATTERNS`. If a query matches a tool-required pattern, immediately return `False` (not conversational).

4. **Enhance LLM Prompt with Explicit Weather Examples**: Update the slow-path LLM prompt to include a dedicated section that explicitly lists weather queries as tool-requiring.
   - Add explicit examples: "che tempo fa a [città]", "meteo [città]", "weather in [city]", "temperature [city]"
   - Add a bullet point: "Query meteo/weather → richiede API meteo → NON conversazionale"

5. **Maintain Existing Pattern Matching Logic**: Ensure all existing conversational patterns continue to work exactly as before, with no changes to their regex or matching behavior.

### Recommended Implementation Strategy

Use the "Separate Tool-Required Patterns" approach (option 3) because:
- It's cleaner and more maintainable than inverting logic
- It makes the intent explicit: some patterns indicate tool requirements
- It allows easy extension for other tool-required patterns in the future (e.g., price queries, news queries)
- It preserves the existing `CONVERSATIONAL_PATTERNS` logic completely unchanged

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that submit weather queries to the ConversationalDetector and assert that they are classified as tool-requiring (is_conversational=False). Run these tests on the UNFIXED code to observe failures and understand the root cause.

**Test Cases**:
1. **Italian Weather Query**: Submit "Che tempo fa a Caltanissetta?" (will fail on unfixed code - returns is_conversational=True)
2. **Short Italian Weather**: Submit "meteo a Roma" (will fail on unfixed code - returns is_conversational=True)
3. **English Weather Query**: Submit "weather in Milan" (will fail on unfixed code - returns is_conversational=True)
4. **Temperature Query**: Submit "temperatura Napoli" (will fail on unfixed code - returns is_conversational=True)
5. **Forecast Query**: Submit "previsioni Milano" (will fail on unfixed code - returns is_conversational=True)
6. **Edge Case - Ambiguous**: Submit "come va il tempo?" (may fail on unfixed code - context-dependent)

**Expected Counterexamples**:
- All weather queries return is_conversational=True when they should return False
- Possible causes: no weather pattern in fast-path, LLM prompt ambiguity, pattern matching order

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := is_conversational_fixed(input)
  ASSERT result.is_conversational == False
  ASSERT result.reason CONTAINS "weather" OR "tool_required"
END FOR
```

**Test Cases**:
- Test all weather keyword variations (tempo, meteo, previsioni, temperatura, clima, weather, forecast, temperature, climate)
- Test weather queries in different sentence structures ("che tempo fa", "meteo a", "weather in", "temperatura")
- Test mixed-language queries if applicable
- Test edge cases (very short queries like "meteo?", queries with multiple keywords)

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT is_conversational_original(input) = is_conversational_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-weather inputs

**Test Plan**: Observe behavior on UNFIXED code first for conversational queries and other tool queries, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Greeting Preservation**: Observe that "ciao", "hello", "buongiorno" are classified as conversational on unfixed code, then verify this continues after fix
2. **Farewell Preservation**: Observe that "arrivederci", "grazie", "bye" are classified as conversational on unfixed code, then verify this continues after fix
3. **Small Talk Preservation**: Observe that "come stai", "how are you" are classified as conversational on unfixed code, then verify this continues after fix
4. **Meta Question Preservation**: Observe that "chi sei", "cosa puoi fare" are classified as conversational on unfixed code, then verify this continues after fix
5. **Other Tool Queries Preservation**: Observe that "prezzo bitcoin", "terremoti recenti", "cerca notizie" are classified as tool-requiring on unfixed code, then verify this continues after fix

### Unit Tests

- Test each weather keyword individually in isolation
- Test weather queries with different city names and locations
- Test edge cases: empty string, single word "meteo", very long weather queries
- Test that existing conversational patterns still match correctly
- Test that non-weather tool queries still classify as tool-requiring

### Property-Based Tests

- Generate random queries with weather keywords and verify they are classified as tool-requiring
- Generate random conversational queries (greetings, farewells, small talk) and verify they are still classified as conversational
- Generate random non-weather tool queries and verify they are still classified as tool-requiring
- Test across many language variations and sentence structures

### Integration Tests

- Test full flow: weather query → classified as tool-requiring → routed to geo_weather domain → openmeteo_weather tool called
- Test that conversational queries still bypass tool routing after fix
- Test that other tool queries (prices, earthquakes, news) still route correctly after fix
- Test switching between conversational and weather queries in a conversation
