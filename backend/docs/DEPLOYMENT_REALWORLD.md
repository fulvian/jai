# Real-World Deployment Guide: Unified Intent Analysis

## Overview

This guide provides step-by-step instructions for deploying the UnifiedIntentAnalyzer system for real-world testing. The system is production-ready with feature flags for safe gradual rollout.

## Pre-Deployment Checklist

- [ ] All tests passing (70 tests across 3 test files)
- [ ] Code reviewed and merged to main branch
- [ ] Environment variables configured
- [ ] Monitoring infrastructure ready
- [ ] Rollback procedures documented
- [ ] Team trained on new system

## Quick Start (5 minutes)

### 1. Enable the Feature Flag

```bash
# In your .env file or environment
export USE_UNIFIED_INTENT_ANALYZER=true
export UNIFIED_INTENT_ROLLOUT_PHASE=disabled  # Start disabled
export UNIFIED_INTENT_TRAFFIC_PERCENTAGE=0
```

### 2. Verify Installation

```bash
# Run the test suite
cd Me4BrAIn
python -m pytest tests/engine/test_unified_intent_analyzer.py -v
python -m pytest tests/engine/test_unified_intent_properties.py -v
python -m pytest tests/engine/test_unified_intent_integration.py -v

# Expected: 70 tests passing ✅
```

### 3. Start the Application

```bash
# Start the Me4BrAIn backend
python -m me4brain.main

# Start the PersAn frontend (in another terminal)
cd ../PersAn
npm run dev
```

### 4. Test a Weather Query

Open the web UI and send:
```
Che tempo fa a Caltanissetta?
```

Expected behavior:
- System should classify as TOOL_REQUIRED
- Domain should be geo_weather
- Should retrieve actual weather data
- Should respond with real weather information

## Deployment Phases

### Phase 1: Disabled (0% Traffic) - Week 1

**Goal**: Verify system stability with feature flag disabled

**Configuration**:
```bash
export USE_UNIFIED_INTENT_ANALYZER=true
export UNIFIED_INTENT_ROLLOUT_PHASE=disabled
export UNIFIED_INTENT_TRAFFIC_PERCENTAGE=0
```

**Actions**:
1. Deploy code to staging environment
2. Run full test suite
3. Monitor system logs for errors
4. Verify no traffic routed to new system
5. Establish baseline metrics

**Success Criteria**:
- No errors in logs
- All tests passing
- System stable for 24 hours
- Baseline metrics recorded

### Phase 2: Canary (10% Traffic) - Week 2

**Goal**: Test with real users, catch edge cases

**Configuration**:
```bash
export USE_UNIFIED_INTENT_ANALYZER=true
export UNIFIED_INTENT_ROLLOUT_PHASE=canary
export UNIFIED_INTENT_TRAFFIC_PERCENTAGE=10
```

**Actions**:
1. Enable for 10% of users
2. Monitor metrics closely
3. Collect user feedback
4. Compare with baseline
5. Fix any issues discovered

**Metrics to Monitor**:
- Accuracy: Weather (target: ≥95%), Conversational (target: ≥98%)
- Latency: p95 (target: <200ms)
- Error rate: (target: <1%)
- Cache hit rate: (target: >40%)

**Success Criteria**:
- Accuracy ≥ 95% for weather queries
- Accuracy ≥ 98% for conversational queries
- p95 latency < 200ms
- Error rate < 1%
- No user complaints

### Phase 3: Beta (50% Traffic) - Week 3

**Goal**: Validate with larger user base

**Configuration**:
```bash
export USE_UNIFIED_INTENT_ANALYZER=true
export UNIFIED_INTENT_ROLLOUT_PHASE=beta
export UNIFIED_INTENT_TRAFFIC_PERCENTAGE=50
```

**Actions**:
1. Enable for 50% of users
2. Monitor metrics continuously
3. Collect comprehensive feedback
4. Compare with Phase 2 metrics
5. Fix any issues discovered

**Success Criteria**:
- All Phase 2 criteria still met
- Positive user feedback
- No regression in performance
- Cache hit rate > 40%

### Phase 4: Production (100% Traffic) - Week 4+

**Goal**: Full production deployment

**Configuration**:
```bash
export USE_UNIFIED_INTENT_ANALYZER=true
export UNIFIED_INTENT_ROLLOUT_PHASE=production
export UNIFIED_INTENT_TRAFFIC_PERCENTAGE=100
```

**Actions**:
1. Enable for 100% of users
2. Monitor for 2 weeks
3. Verify all SLOs met
4. Collect final metrics
5. Remove feature flag

**Success Criteria**:
- All previous criteria met
- Stable for 2 weeks
- All SLOs achieved
- Ready to remove feature flag

## Configuration Reference

### Environment Variables

```bash
# Feature Flag
USE_UNIFIED_INTENT_ANALYZER=true|false          # Enable/disable system
UNIFIED_INTENT_ROLLOUT_PHASE=disabled|canary|beta|production
UNIFIED_INTENT_TRAFFIC_PERCENTAGE=0-100         # Traffic percentage

# Intent Analysis
INTENT_ANALYSIS_TIMEOUT=5.0                     # Timeout in seconds
INTENT_ANALYSIS_MODEL=model_routing             # LLM model to use
INTENT_CACHE_TTL=300                            # Cache TTL in seconds

# Cache Configuration
INTENT_CACHE_MAX_SIZE=10000                     # Max cache entries
INTENT_CACHE_TTL=300                            # Cache TTL in seconds

# Batch Processing
INTENT_BATCH_SIZE=10                            # Batch size
INTENT_BATCH_TIMEOUT_MS=100                     # Batch timeout in ms
```

### Python Configuration

```python
from me4brain.llm.config import get_llm_config

config = get_llm_config()

# Check if enabled
if config.use_unified_intent_analyzer:
    print("UnifiedIntentAnalyzer is enabled")

# Check rollout phase
from me4brain.engine.feature_flags import get_feature_flag_manager
ffm = get_feature_flag_manager()
print(f"Current phase: {ffm.current_phase}")
print(f"Traffic percentage: {ffm.traffic_percentage}%")
```

## Monitoring Setup

### Key Metrics to Track

1. **Query Volume**
   - Queries per minute
   - By query type (weather, conversational, multi-domain)
   - By phase (disabled, canary, beta, production)

2. **Accuracy**
   - Weather queries: target ≥ 95%
   - Conversational queries: target ≥ 98%
   - Multi-domain queries: target ≥ 90%

3. **Performance**
   - p50 latency: target 100ms
   - p95 latency: target 200ms
   - p99 latency: target 250ms
   - Throughput: target 100 queries/sec

4. **Reliability**
   - Error rate: target < 1%
   - Cache hit rate: target > 40%
   - LLM API availability: target > 99%

5. **User Feedback**
   - Misclassification reports
   - Support tickets
   - User satisfaction

### Monitoring Commands

```bash
# View current metrics
python -c "
from me4brain.engine.intent_monitoring import get_intent_monitor
monitor = get_intent_monitor()
print(monitor.get_metrics())
"

# View cache statistics
python -c "
from me4brain.engine.intent_cache import get_intent_cache
cache = get_intent_cache()
print(cache.get_stats())
"

# View feature flag status
python -c "
from me4brain.engine.feature_flags import get_feature_flag_manager
ffm = get_feature_flag_manager()
print(f'Phase: {ffm.current_phase}')
print(f'Traffic: {ffm.traffic_percentage}%')
print(f'Metrics: {ffm.get_metrics()}')
"
```

## Troubleshooting

### Issue: Weather queries still classified as conversational

**Diagnosis**:
```bash
# Check if feature flag is enabled
echo $USE_UNIFIED_INTENT_ANALYZER

# Check if traffic is routed to new system
python -c "
from me4brain.engine.feature_flags import get_feature_flag_manager
ffm = get_feature_flag_manager()
print(f'Phase: {ffm.current_phase}')
print(f'Traffic: {ffm.traffic_percentage}%')
"
```

**Solution**:
1. Verify `USE_UNIFIED_INTENT_ANALYZER=true`
2. Verify `UNIFIED_INTENT_ROLLOUT_PHASE` is not `disabled`
3. Verify `UNIFIED_INTENT_TRAFFIC_PERCENTAGE > 0`
4. Check logs for errors in intent analysis
5. Verify LLM model is responding correctly

### Issue: High latency (p95 > 200ms)

**Diagnosis**:
```bash
# Check cache hit rate
python -c "
from me4brain.engine.intent_cache import get_intent_cache
cache = get_intent_cache()
stats = cache.get_stats()
print(f'Hit rate: {stats.hit_rate:.1%}')
print(f'Avg latency: {stats.avg_latency_ms:.1f}ms')
"
```

**Solution**:
1. Increase cache size: `INTENT_CACHE_MAX_SIZE=20000`
2. Increase cache TTL: `INTENT_CACHE_TTL=600`
3. Enable batch processing: `INTENT_BATCH_SIZE=10`
4. Check LLM model performance
5. Consider using faster model (Mistral Small)

### Issue: High error rate (> 1%)

**Diagnosis**:
```bash
# Check error metrics
python -c "
from me4brain.engine.intent_monitoring import get_intent_monitor
monitor = get_intent_monitor()
metrics = monitor.get_metrics()
print(f'Error rate: {metrics[\"error_rate\"]:.1%}')
print(f'Errors: {metrics[\"total_errors\"]}')
"
```

**Solution**:
1. Check LLM API availability
2. Verify network connectivity
3. Check error logs for patterns
4. Increase timeout: `INTENT_ANALYSIS_TIMEOUT=10.0`
5. Enable fallback to old system

### Issue: Low accuracy (< 90%)

**Diagnosis**:
```bash
# Check accuracy by query type
python -c "
from me4brain.engine.intent_monitoring import get_intent_monitor
monitor = get_intent_monitor()
metrics = monitor.get_metrics()
print(f'Weather accuracy: {metrics[\"weather_accuracy\"]:.1%}')
print(f'Conversational accuracy: {metrics[\"conversational_accuracy\"]:.1%}')
print(f'Multi-domain accuracy: {metrics[\"multi_domain_accuracy\"]:.1%}')
"
```

**Solution**:
1. Review misclassified queries
2. Update domain definitions in prompt
3. Adjust confidence thresholds
4. Collect more training examples
5. Consider fine-tuning LLM model

## Rollback Procedure

If issues are discovered, rollback is simple:

```bash
# Option 1: Disable feature flag
export USE_UNIFIED_INTENT_ANALYZER=false

# Option 2: Reduce traffic percentage
export UNIFIED_INTENT_TRAFFIC_PERCENTAGE=0

# Option 3: Switch to disabled phase
export UNIFIED_INTENT_ROLLOUT_PHASE=disabled

# Restart application
# System will automatically use old ConversationalDetector
```

## Success Metrics

### Accuracy Targets
- Weather queries: ≥ 95%
- Conversational queries: ≥ 98%
- Multi-domain queries: ≥ 90%
- Overall: ≥ 95%

### Performance Targets
- p50 latency: 100ms
- p95 latency: 200ms
- p99 latency: 250ms
- Throughput: 100 queries/sec
- Cache hit rate: > 40%

### Reliability Targets
- Error rate: < 1%
- Uptime: > 99.9%
- LLM API availability: > 99%

### User Satisfaction
- No increase in support tickets
- Positive user feedback
- No regression in user experience

## Next Steps

1. **Week 1**: Deploy Phase 1 (disabled), verify stability
2. **Week 2**: Deploy Phase 2 (10% traffic), monitor metrics
3. **Week 3**: Deploy Phase 3 (50% traffic), collect feedback
4. **Week 4+**: Deploy Phase 4 (100% traffic), monitor for 2 weeks
5. **After 2 weeks**: Remove feature flag, clean up old code

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review logs in `logs/` directory
3. Check metrics using monitoring commands
4. Consult RUNBOOK.md for common issues
5. Contact the development team

## See Also

- [GRADUAL_ROLLOUT.md](./GRADUAL_ROLLOUT.md) - Detailed rollout strategy
- [DEPLOYMENT_CHECKLIST.md](./DEPLOYMENT_CHECKLIST.md) - Pre-deployment checklist
- [RUNBOOK.md](./RUNBOOK.md) - Common issues and solutions
- [MONITORING.md](./MONITORING.md) - Monitoring setup guide
- [ERROR_HANDLING.md](./ERROR_HANDLING.md) - Error handling procedures
