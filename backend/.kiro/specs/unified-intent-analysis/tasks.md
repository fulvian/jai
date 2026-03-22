# Tasks: Unified Intent Analysis

## Phase 1: Core Implementation

### 1. Create UnifiedIntentAnalyzer Component

- [ ] 1.1 Create src/me4brain/engine/unified_intent_analyzer.py file
- [ ] 1.2 Implement IntentType enum (CONVERSATIONAL, TOOL_REQUIRED)
- [ ] 1.3 Implement QueryComplexity enum (SIMPLE, MODERATE, COMPLEX)
- [ ] 1.4 Implement IntentAnalysis dataclass with validation
- [ ] 1.5 Implement UnifiedIntentAnalyzer class with __init__
- [ ] 1.6 Implement _build_intent_prompt() method with domain definitions
- [ ] 1.7 Implement analyze() method with LLM classification
- [ ] 1.8 Implement JSON parsing and validation logic
- [ ] 1.9 Implement error handling with fallback behavior
- [ ] 1.10 Add structured logging for all operations

### 2. Integrate with ToolCallingEngine

- [ ] 2.1 Import UnifiedIntentAnalyzer in src/me4brain/engine/core.py
- [ ] 2.2 Add analyzer initialization in ToolCallingEngine.__init__
- [ ] 2.3 Add analyzer initialization in _create_with_hybrid_routing factory
- [ ] 2.4 Replace _check_conversational_bypass() calls with analyzer.analyze()
- [ ] 2.5 Update run() method to use intent analysis results
- [ ] 2.6 Update run_iterative() method to use intent analysis results
- [ ] 2.7 Update run_iterative_stream() method to use intent analysis results
- [ ] 2.8 Remove _check_conversational_bypass() method entirely
- [ ] 2.9 Update conversational query handling to use intent analysis
- [ ] 2.10 Update tool-required query handling to use domains from intent analysis

### 3. Update Configuration

- [ ] 3.1 Add intent_analysis_timeout to config (default: 5s)
- [ ] 3.2 Add intent_cache_ttl to config (default: 300s)
- [ ] 3.3 Add intent_analysis_model to config (default: model_routing)
- [ ] 3.4 Update LLM config to support intent analysis settings
- [ ] 3.5 Add feature flag for gradual rollout (use_unified_intent_analyzer)

## Phase 2: Testing

### 4. Unit Tests

- [ ] 4.1 Create tests/engine/test_unified_intent_analyzer.py
- [ ] 4.2 Test weather query classification (Italian and English)
- [ ] 4.3 Test conversational query classification (greetings, farewells, small talk)
- [ ] 4.4 Test price query classification
- [ ] 4.5 Test search query classification
- [ ] 4.6 Test multi-domain query classification
- [ ] 4.7 Test complexity assessment (simple, moderate, complex)
- [ ] 4.8 Test confidence score calculation
- [ ] 4.9 Test error handling (LLM failure, JSON parse failure, empty query)
- [ ] 4.10 Test prompt construction with and without context

### 5. Property-Based Tests

- [ ] 5.1 Install hypothesis library for property-based testing
- [ ] 5.2 Create tests/engine/test_unified_intent_properties.py
- [ ] 5.3 Test property: Weather keywords → tool_required + geo_weather
- [ ] 5.4 Test property: Conversational patterns → conversational + empty domains
- [ ] 5.5 Test property: Domain consistency (conversational ⟺ empty domains)
- [ ] 5.6 Test property: Confidence bounds (0.0 ≤ confidence ≤ 1.0)
- [ ] 5.7 Test property: Intent type validity (only CONVERSATIONAL or TOOL_REQUIRED)
- [ ] 5.8 Test property: Complexity validity (only SIMPLE, MODERATE, or COMPLEX)

### 6. Integration Tests

- [ ] 6.1 Create tests/engine/test_unified_intent_integration.py
- [ ] 6.2 Test full pipeline: weather query → intent → tools → execution → synthesis
- [ ] 6.3 Test full pipeline: conversational query → intent → direct response
- [ ] 6.4 Test full pipeline: multi-domain query → intent → multiple tools → synthesis
- [ ] 6.5 Test switching between conversational and tool queries in conversation
- [ ] 6.6 Test error scenarios with full pipeline
- [ ] 6.7 Test performance (latency, throughput)
- [ ] 6.8 Test caching behavior

## Phase 3: Migration and Cleanup

### 7. Deprecate ConversationalDetector

- [ ] 7.1 Add deprecation warning to ConversationalDetector class
- [ ] 7.2 Update documentation to recommend UnifiedIntentAnalyzer
- [ ] 7.3 Create migration guide for users of ConversationalDetector
- [ ] 7.4 Add feature flag to switch between old and new systems
- [ ] 7.5 Update all references to ConversationalDetector in codebase

### 8. Documentation

- [ ] 8.1 Update README.md with UnifiedIntentAnalyzer usage
- [ ] 8.2 Create docs/unified-intent-analysis.md with detailed guide
- [ ] 8.3 Update API documentation for ToolCallingEngine
- [ ] 8.4 Add examples for common use cases
- [ ] 8.5 Document migration strategy from ConversationalDetector
- [ ] 8.6 Update architecture diagrams
- [ ] 8.7 Document performance characteristics
- [ ] 8.8 Document error handling and fallback behavior

### 9. Monitoring and Observability

- [ ] 9.1 Add metrics for intent classification (accuracy, latency, error rate)
- [ ] 9.2 Add structured logging for all intent analysis operations
- [ ] 9.3 Add dashboards for monitoring intent analysis performance
- [ ] 9.4 Add alerts for high error rates or latency
- [ ] 9.5 Add telemetry for domain distribution
- [ ] 9.6 Add telemetry for complexity distribution
- [ ] 9.7 Add cache hit rate metrics

## Phase 4: Deployment

### 10. Gradual Rollout

- [ ] 10.1 Deploy with feature flag disabled (0% traffic)
- [ ] 10.2 Enable for 10% of traffic and monitor for 1 week
- [ ] 10.3 Compare metrics: accuracy, latency, error rate
- [ ] 10.4 Fix any issues discovered in 10% rollout
- [ ] 10.5 Enable for 50% of traffic and monitor for 1 week
- [ ] 10.6 Compare metrics and collect user feedback
- [ ] 10.7 Fix any issues discovered in 50% rollout
- [ ] 10.8 Enable for 100% of traffic
- [ ] 10.9 Monitor for 2 weeks with full traffic
- [ ] 10.10 Remove feature flag and ConversationalDetector code

### 11. Performance Optimization

- [ ] 11.1 Implement caching for identical queries
- [ ] 11.2 Optimize LLM prompt for faster inference
- [ ] 11.3 Implement connection pooling for LLM client
- [ ] 11.4 Add batch processing for multiple queries
- [ ] 11.5 Optimize JSON parsing performance
- [ ] 11.6 Profile and optimize hot paths
- [ ] 11.7 Load test with 1000 queries per minute
- [ ] 11.8 Optimize memory usage

## Phase 5: Future Enhancements

### 12. Advanced Features

- [ ] 12.1 Implement multi-turn context tracking
- [ ] 12.2 Implement user preference learning
- [ ] 12.3 Implement confidence-based routing (ask user if low confidence)
- [ ] 12.4 Implement dynamic threshold adjustment
- [ ] 12.5 Implement user feedback loop for accuracy improvement
- [ ] 12.6 Implement automatic domain discovery from tool catalog
- [ ] 12.7 Implement domain hierarchy for better classification
- [ ] 12.8 Implement A/B testing framework for prompt optimization

### 13. Scalability Improvements

- [ ] 13.1 Support 50+ domains without performance degradation
- [ ] 13.2 Implement distributed caching (Redis)
- [ ] 13.3 Implement horizontal scaling for intent analysis
- [ ] 13.4 Optimize for high-throughput scenarios (10k+ queries/min)
- [ ] 13.5 Implement rate limiting per user
- [ ] 13.6 Implement circuit breaker for LLM API failures
- [ ] 13.7 Implement fallback to local model if cloud API fails

## Notes

- All tasks should be completed in order within each phase
- Each task should include appropriate tests
- All code should follow existing code style and conventions
- All changes should be backward compatible
- Feature flags should be used for gradual rollout
- Comprehensive logging should be added for debugging
- Performance should be monitored at each phase
