# Requirements Document: Unified Intent Analysis

## Introduction

This document specifies the functional and non-functional requirements for the Unified Intent Analysis system. The system replaces the current conversational bypass mechanism with an LLM-based intent analyzer that intelligently classifies queries as conversational or tool-requiring, eliminating hardcoded patterns and enabling scalable tool routing across all domains.

## Functional Requirements

### FR1: Intent Classification

**FR1.1** The system SHALL analyze every user query to determine intent type (conversational or tool_required)

**FR1.2** The system SHALL use LLM-based classification for intent determination, not regex patterns

**FR1.3** The system SHALL classify queries containing weather keywords (tempo, meteo, previsioni, temperatura, clima, weather, forecast, temperature, climate) as tool_required with geo_weather domain

**FR1.4** The system SHALL classify queries containing price keywords (prezzo, price, cost, costo) as tool_required with appropriate domain (finance_crypto or shopping)

**FR1.5** The system SHALL classify queries containing search keywords (cerca, search, trova, find, notizie, news) as tool_required with web_search domain

**FR1.6** The system SHALL classify greeting queries (ciao, hello, hi, buongiorno, buonasera) as conversational

**FR1.7** The system SHALL classify farewell queries (arrivederci, bye, grazie, thanks) as conversational

**FR1.8** The system SHALL classify small talk queries (come stai, how are you, come va) as conversational

**FR1.9** The system SHALL classify meta questions (chi sei, what are you, cosa puoi fare) as conversational

**FR1.10** The system SHALL return confidence score (0.0 to 1.0) for each classification

### FR2: Domain Identification

**FR2.1** The system SHALL identify relevant domains for tool-required queries

**FR2.2** The system SHALL return empty domains list for conversational queries

**FR2.3** The system SHALL support multi-domain queries (e.g., weather + prices)

**FR2.4** The system SHALL map queries to available domains: geo_weather, finance_crypto, web_search, communication, scheduling, file_management, data_analysis, travel, food, entertainment, sports, shopping

**FR2.5** The system SHALL filter out invalid domains not in the available domains list

### FR3: Complexity Assessment

**FR3.1** The system SHALL assess query complexity as simple, moderate, or complex

**FR3.2** The system SHALL classify single-tool, single-domain queries as simple

**FR3.3** The system SHALL classify multiple-tool, single-domain queries as moderate

**FR3.4** The system SHALL classify multiple-tool, multiple-domain queries as complex

### FR4: Engine Integration

**FR4.1** The system SHALL integrate UnifiedIntentAnalyzer as the first step in ToolCallingEngine.run()

**FR4.2** The system SHALL remove the _check_conversational_bypass() method from ToolCallingEngine

**FR4.3** The system SHALL route conversational queries to direct LLM response without tool execution

**FR4.4** The system SHALL route tool-required queries to ToolRetriever with identified domains

**FR4.5** The system SHALL maintain backward compatibility with existing tool routing behavior

### FR5: Response Generation

**FR5.1** For conversational queries, the system SHALL generate direct LLM responses without tool execution

**FR5.2** For tool-required queries, the system SHALL retrieve relevant tools, execute them, and synthesize results

**FR5.3** The system SHALL return EngineResponse with answer, tool_results, tools_called, and total_latency_ms

**FR5.4** For conversational queries, the system SHALL return empty tool_results and tools_called lists

### FR6: Error Handling

**FR6.1** The system SHALL handle LLM API failures gracefully with fallback to safe default (tool_required, general domain)

**FR6.2** The system SHALL handle JSON parse failures with fallback to safe default

**FR6.3** The system SHALL log all errors with structured logging (query preview, error type, error message)

**FR6.4** The system SHALL handle empty queries by returning conversational intent

**FR6.5** The system SHALL validate LLM response structure and reject invalid responses

## Non-Functional Requirements

### NFR1: Performance

**NFR1.1** Intent analysis SHALL complete within 200ms for 95% of queries

**NFR1.2** The system SHALL add no more than 100ms overhead compared to current conversational bypass for conversational queries

**NFR1.3** The system SHALL support at least 100 concurrent intent analysis requests

**NFR1.4** The system SHALL cache intent analysis results for identical queries within a session

### NFR2: Accuracy

**NFR2.1** The system SHALL achieve at least 95% accuracy for weather query classification

**NFR2.2** The system SHALL achieve at least 98% accuracy for conversational query classification

**NFR2.3** The system SHALL achieve at least 90% accuracy for multi-domain query classification

**NFR2.4** The system SHALL maintain at least 95% accuracy for all existing tool-requiring query types

### NFR3: Scalability

**NFR3.1** The system SHALL support adding new domains without code changes (only prompt updates)

**NFR3.2** The system SHALL support adding new tool categories without hardcoded patterns

**NFR3.3** The system SHALL scale to at least 50 domains without performance degradation

**NFR3.4** The system SHALL handle at least 1000 queries per minute

### NFR4: Maintainability

**NFR4.1** The system SHALL use structured logging for all intent analysis operations

**NFR4.2** The system SHALL provide clear error messages for debugging

**NFR4.3** The system SHALL include comprehensive unit tests with at least 90% code coverage

**NFR4.4** The system SHALL include property-based tests for correctness properties

**NFR4.5** The system SHALL include integration tests for full pipeline flows

### NFR5: Security

**NFR5.1** The system SHALL sanitize user queries before LLM classification

**NFR5.2** The system SHALL limit query length to 1000 characters

**NFR5.3** The system SHALL validate LLM response structure to prevent prompt injection

**NFR5.4** The system SHALL implement rate limiting (100 requests per minute per user)

**NFR5.5** The system SHALL not log full user queries (only previews up to 50 characters)

### NFR6: Reliability

**NFR6.1** The system SHALL have at least 99.9% uptime

**NFR6.2** The system SHALL handle LLM API failures without crashing

**NFR6.3** The system SHALL implement exponential backoff for LLM API retries

**NFR6.4** The system SHALL provide fallback behavior for all error scenarios

### NFR7: Observability

**NFR7.1** The system SHALL log intent classification results (intent, domains, confidence, reasoning)

**NFR7.2** The system SHALL track metrics: classification latency, accuracy, error rate, cache hit rate

**NFR7.3** The system SHALL provide structured logs compatible with log aggregation tools

**NFR7.4** The system SHALL emit events for monitoring: intent_analyzed, classification_failed, fallback_triggered

## Acceptance Criteria

### AC1: Weather Query Classification

**AC1.1** GIVEN a user query "Che tempo fa a Caltanissetta?" WHEN the system analyzes intent THEN it SHALL return intent=tool_required, domains=["geo_weather"], confidence>0.8

**AC1.2** GIVEN a user query "meteo a Roma" WHEN the system analyzes intent THEN it SHALL return intent=tool_required, domains=["geo_weather"]

**AC1.3** GIVEN a user query "weather in Milan" WHEN the system analyzes intent THEN it SHALL return intent=tool_required, domains=["geo_weather"]

**AC1.4** GIVEN a user query "temperatura Napoli" WHEN the system analyzes intent THEN it SHALL return intent=tool_required, domains=["geo_weather"]

### AC2: Conversational Query Classification

**AC2.1** GIVEN a user query "ciao" WHEN the system analyzes intent THEN it SHALL return intent=conversational, domains=[]

**AC2.2** GIVEN a user query "come stai?" WHEN the system analyzes intent THEN it SHALL return intent=conversational, domains=[]

**AC2.3** GIVEN a user query "chi sei?" WHEN the system analyzes intent THEN it SHALL return intent=conversational, domains=[]

**AC2.4** GIVEN a user query "grazie" WHEN the system analyzes intent THEN it SHALL return intent=conversational, domains=[]

### AC3: Multi-Domain Query Classification

**AC3.1** GIVEN a user query "Che tempo fa a Roma e qual è il prezzo del Bitcoin?" WHEN the system analyzes intent THEN it SHALL return intent=tool_required, domains=["geo_weather", "finance_crypto"], complexity=complex

**AC3.2** GIVEN a user query "cerca notizie sul meteo" WHEN the system analyzes intent THEN it SHALL return intent=tool_required, domains=["web_search", "geo_weather"]

### AC4: Engine Integration

**AC4.1** GIVEN a weather query WHEN ToolCallingEngine.run() is called THEN it SHALL call UnifiedIntentAnalyzer, retrieve weather tools, execute them, and return weather data

**AC4.2** GIVEN a conversational query WHEN ToolCallingEngine.run() is called THEN it SHALL call UnifiedIntentAnalyzer, generate direct response, and return empty tools_called list

**AC4.3** GIVEN any query WHEN ToolCallingEngine.run() is called THEN it SHALL NOT call _check_conversational_bypass() (method removed)

### AC5: Error Handling

**AC5.1** GIVEN LLM API failure WHEN intent analysis is attempted THEN it SHALL return fallback IntentAnalysis with intent=tool_required, domains=["general"], confidence=0.5

**AC5.2** GIVEN invalid JSON response WHEN parsing LLM output THEN it SHALL return fallback IntentAnalysis and log warning

**AC5.3** GIVEN empty query WHEN intent analysis is attempted THEN it SHALL return intent=conversational, domains=[], confidence=1.0

### AC6: Performance

**AC6.1** GIVEN 100 concurrent weather queries WHEN intent analysis is performed THEN 95% SHALL complete within 200ms

**AC6.2** GIVEN identical query submitted twice in same session WHEN intent analysis is performed THEN second call SHALL use cached result

### AC7: Backward Compatibility

**AC7.1** GIVEN existing tool-requiring queries (prices, earthquakes, news) WHEN system is deployed THEN they SHALL continue to be classified as tool_required and route correctly

**AC7.2** GIVEN existing conversational queries WHEN system is deployed THEN they SHALL continue to be classified as conversational

## Constraints

### Technical Constraints

**C1** The system MUST use existing LLM infrastructure (me4brain.llm.base.LLMProvider)

**C2** The system MUST integrate with existing ToolCallingEngine without breaking API

**C3** The system MUST use structured logging (structlog)

**C4** The system MUST support both local (Ollama) and cloud (NanoGPT) LLM providers

### Business Constraints

**C5** The system MUST maintain backward compatibility with existing tool routing

**C6** The system MUST not increase latency by more than 100ms for conversational queries

**C7** The system MUST be deployable with gradual rollout (10% → 50% → 100%)

### Regulatory Constraints

**C8** The system MUST comply with GDPR for user query logging

**C9** The system MUST anonymize queries in telemetry

**C10** The system MUST not store full user queries beyond session duration

## Dependencies

### Internal Dependencies

- me4brain.llm.base.LLMProvider
- me4brain.llm.models (LLMRequest, Message, MessageRole)
- me4brain.llm.config (get_llm_config)
- me4brain.engine.types (EngineResponse, ToolResult, ToolTask)
- me4brain.engine.executor.ParallelExecutor
- me4brain.engine.synthesizer.ResponseSynthesizer

### External Dependencies

- structlog (structured logging)
- pydantic (data validation)
- hypothesis (property-based testing)

## Risks and Mitigations

### Risk 1: LLM Classification Accuracy

**Risk**: LLM may misclassify edge cases
**Impact**: High - incorrect routing leads to poor user experience
**Mitigation**: Comprehensive testing, confidence thresholds, user feedback loop

### Risk 2: Increased Latency

**Risk**: LLM call adds latency to every query
**Impact**: Medium - slower response times
**Mitigation**: Fast model selection, caching, parallel execution

### Risk 3: LLM API Failures

**Risk**: LLM API may be unavailable
**Impact**: High - system cannot classify queries
**Mitigation**: Fallback to safe default, retry logic, monitoring

### Risk 4: Prompt Injection

**Risk**: Malicious users may attempt prompt injection
**Impact**: Medium - system may be manipulated
**Mitigation**: Structured JSON output, response validation, input sanitization

### Risk 5: Migration Issues

**Risk**: New system may break existing functionality
**Impact**: High - production outage
**Mitigation**: Gradual rollout, feature flags, automated rollback, comprehensive testing

## Success Metrics

### Metric 1: Classification Accuracy

**Target**: 95% accuracy for weather queries, 98% for conversational queries
**Measurement**: Compare classifications against labeled test set
**Frequency**: Daily

### Metric 2: Latency

**Target**: 95th percentile latency < 200ms for intent analysis
**Measurement**: Track latency distribution in production
**Frequency**: Real-time monitoring

### Metric 3: Error Rate

**Target**: < 1% error rate for intent analysis
**Measurement**: Count failed classifications / total classifications
**Frequency**: Real-time monitoring

### Metric 4: User Satisfaction

**Target**: No increase in user complaints about misclassification
**Measurement**: Track support tickets related to query routing
**Frequency**: Weekly

### Metric 5: Scalability

**Target**: Support 50+ domains without performance degradation
**Measurement**: Load testing with increasing domain count
**Frequency**: Before each major release

## Glossary

- **Intent**: The purpose of a user query (conversational or tool_required)
- **Domain**: A category of tools (e.g., geo_weather, finance_crypto)
- **Complexity**: The difficulty level of a query (simple, moderate, complex)
- **Conversational Bypass**: The current mechanism that checks for conversational queries before routing
- **UnifiedIntentAnalyzer**: The new component that replaces conversational bypass
- **Tool-Required**: Queries that need external tools/APIs to answer
- **Conversational**: Queries that can be answered directly without tools
- **LLM**: Large Language Model used for classification
- **Confidence**: A score (0.0-1.0) indicating classification certainty
