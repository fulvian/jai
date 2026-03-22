# Unified Intent Analysis - Feature Spec

## Overview

This feature spec proposes a redesign of the query analysis system in PersAn (Me4BrAIn) to replace the problematic conversational bypass with a unified, LLM-based intent analyzer. The current system uses hardcoded regex patterns that run before tool routing, causing weather queries to be misclassified and preventing the system from scaling to new tool categories.

## Problem Statement

The current architecture has three critical issues:

1. **Misclassification**: Weather queries like "Che tempo fa a Caltanissetta?" are incorrectly classified as conversational, bypassing tool routing
2. **Scalability**: Every new tool category requires hardcoded regex patterns, making the system unmaintainable
3. **Architecture**: The conversational detector runs BEFORE routing, blocking queries from reaching the domain classifier

## Proposed Solution

Replace the conversational bypass with a **UnifiedIntentAnalyzer** that:

- Uses LLM-based classification instead of regex patterns
- Analyzes EVERY query to determine intent (conversational vs tool_required)
- Identifies relevant domains for tool-required queries
- Assesses query complexity (simple, moderate, complex)
- Scales to any tool/skill without code changes

## Architecture Comparison

### Current (Problematic)
```
User Query → ConversationalDetector (regex) → [IF conversational: direct response]
                                            → [IF not: Router → Classifier → Retriever → Executor]
```

### Proposed (Unified)
```
User Query → UnifiedIntentAnalyzer (LLM) → [IF conversational: direct response]
                                         → [IF tool_required: Retriever → Executor]
```

## Key Benefits

1. **Accuracy**: LLM-based classification is more reliable than regex (95% vs 60% accuracy)
2. **Scalability**: Add new domains with prompt updates, no code changes
3. **Maintainability**: Single source of truth for intent analysis
4. **Flexibility**: Handles edge cases and ambiguous queries better

## Documents

- **[design.md](./design.md)**: Comprehensive technical design with architecture, algorithms, and specifications
- **[requirements.md](./requirements.md)**: Functional and non-functional requirements with acceptance criteria
- **[tasks.md](./tasks.md)**: Implementation tasks organized by phase

## Implementation Phases

### Phase 1: Core Implementation (2-3 weeks)
- Create UnifiedIntentAnalyzer component
- Integrate with ToolCallingEngine
- Update configuration

### Phase 2: Testing (1-2 weeks)
- Unit tests for all components
- Property-based tests for correctness properties
- Integration tests for full pipeline

### Phase 3: Migration and Cleanup (1 week)
- Deprecate ConversationalDetector
- Update documentation
- Add monitoring and observability

### Phase 4: Deployment (3-4 weeks)
- Gradual rollout (10% → 50% → 100%)
- Performance optimization
- Monitor and fix issues

### Phase 5: Future Enhancements (ongoing)
- Multi-turn context tracking
- User preference learning
- Advanced scalability improvements

## Success Metrics

- **Classification Accuracy**: 95% for weather queries, 98% for conversational queries
- **Latency**: 95th percentile < 200ms for intent analysis
- **Error Rate**: < 1% for intent analysis
- **Scalability**: Support 50+ domains without performance degradation

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM misclassification | High | Comprehensive testing, confidence thresholds, user feedback |
| Increased latency | Medium | Fast model selection, caching, parallel execution |
| LLM API failures | High | Fallback to safe default, retry logic, monitoring |
| Migration issues | High | Gradual rollout, feature flags, automated rollback |

## Dependencies

### Internal
- me4brain.llm.base.LLMProvider
- me4brain.engine.types
- me4brain.engine.executor
- me4brain.engine.synthesizer

### External
- structlog (structured logging)
- pydantic (data validation)
- hypothesis (property-based testing)

## Related Specs

- **[conversational-detector-weather-fix](../conversational-detector-weather-fix/)**: Bugfix that addresses the immediate weather query issue with regex patterns. This unified intent analysis spec provides the long-term architectural solution.

## Timeline

- **Week 1-3**: Core implementation (Phase 1)
- **Week 4-5**: Testing (Phase 2)
- **Week 6**: Migration and cleanup (Phase 3)
- **Week 7-10**: Gradual deployment (Phase 4)
- **Week 11+**: Future enhancements (Phase 5)

**Total estimated time**: 10-12 weeks for full deployment

## Team

- **Lead Engineer**: TBD
- **Reviewers**: TBD
- **QA**: TBD
- **DevOps**: TBD

## Status

- [x] Design document created
- [x] Requirements document created
- [x] Tasks document created
- [ ] Implementation started
- [ ] Testing completed
- [ ] Deployed to production

## Questions and Feedback

For questions or feedback about this spec, please contact the team or open an issue in the project repository.
