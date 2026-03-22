# Real-World Test Plan: Unified Intent Analysis

## Overview

This document outlines the testing strategy for validating the UnifiedIntentAnalyzer system in real-world conditions. The plan covers test scenarios, success criteria, and monitoring procedures.

## Test Phases

### Phase 1: Disabled (Week 1)

**Objective**: Establish baseline metrics with old system

**Duration**: 7 days

**Configuration**:
```bash
USE_UNIFIED_INTENT_ANALYZER=false
UNIFIED_INTENT_ROLLOUT_PHASE=disabled
UNIFIED_INTENT_TRAFFIC_PERCENTAGE=0
```

**Test Scenarios**:

1. **Weather Queries**
   - "Che tempo fa a Caltanissetta?"
   - "What's the weather in New York?"
   - "Piove oggi?"
   - "Temperature in London"
   - Expected: Routed to old system, should work

2. **Conversational Queries**
   - "Ciao, come stai?"
   - "Hello, how are you?"
   - "Grazie mille"
   - "Goodbye"
   - Expected: Handled directly, no tools

3. **Multi-Domain Queries**
   - "Che tempo fa a Roma e qual è il prezzo dell'oro?"
   - "Show me weather in Paris and search for restaurants"
   - Expected: Routed to multiple tools

**Metrics to Collect**:
- Query volume by type
- Response latency (p50, p95, p99)
- Error rate
- User satisfaction

**Success Criteria**:
- System stable for 7 days
- Error rate < 1%
- No user complaints
- Baseline metrics established

### Phase 2: Canary (Week 2)

**Objective**: Test new system with 10% of users

**Duration**: 7 days

**Configuration**:
```bash
USE_UNIFIED_INTENT_ANALYZER=true
UNIFIED_INTENT_ROLLOUT_PHASE=canary
UNIFIED_INTENT_TRAFFIC_PERCENTAGE=10
```

**Test Scenarios**:

1. **Weather Queries (Critical)**
   - "Che tempo fa a Caltanissetta?" → Should classify as TOOL_REQUIRED + geo_weather
   - "What's the weather in New York?" → Should classify as TOOL_REQUIRED + geo_weather
   - "Piove oggi?" → Should classify as TOOL_REQUIRED + geo_weather
   - "Temperature in London" → Should classify as TOOL_REQUIRED + geo_weather
   - Expected: 95%+ accuracy

2. **Conversational Queries (Critical)**
   - "Ciao, come stai?" → Should classify as CONVERSATIONAL
   - "Hello, how are you?" → Should classify as CONVERSATIONAL
   - "Grazie mille" → Should classify as CONVERSATIONAL
   - "Goodbye" → Should classify as CONVERSATIONAL
   - Expected: 98%+ accuracy

3. **Price Queries**
   - "Qual è il prezzo dell'oro?" → Should classify as TOOL_REQUIRED + price
   - "What's the price of Bitcoin?" → Should classify as TOOL_REQUIRED + price
   - Expected: 90%+ accuracy

4. **Search Queries**
   - "Cerca ristoranti a Roma" → Should classify as TOOL_REQUIRED + search
   - "Find hotels in Paris" → Should classify as TOOL_REQUIRED + search
   - Expected: 90%+ accuracy

5. **Multi-Domain Queries**
   - "Che tempo fa a Roma e qual è il prezzo dell'oro?" → Should classify as TOOL_REQUIRED + [geo_weather, price]
   - "Show me weather in Paris and search for restaurants" → Should classify as TOOL_REQUIRED + [geo_weather, search]
   - Expected: 85%+ accuracy

6. **Edge Cases**
   - Empty query → Should handle gracefully
   - Very long query → Should handle gracefully
   - Special characters → Should handle gracefully
   - Mixed languages → Should handle gracefully

**Metrics to Collect**:
- Accuracy by query type
- Latency (p50, p95, p99)
- Cache hit rate
- Error rate
- Domain distribution
- Confidence scores

**Monitoring**:
```bash
# Start monitoring dashboard
python scripts/monitor_intent.py

# Check metrics every hour
python -c "
from me4brain.engine.intent_monitoring import get_intent_monitor
monitor = get_intent_monitor()
print(monitor.get_metrics())
"
```

**Success Criteria**:
- Weather accuracy ≥ 95%
- Conversational accuracy ≥ 98%
- Multi-domain accuracy ≥ 85%
- p95 latency < 200ms
- Error rate < 1%
- Cache hit rate > 30%
- No user complaints

**Rollback Trigger**:
- Accuracy < 90% for any query type
- Error rate > 2%
- p95 latency > 300ms
- More than 5 user complaints

### Phase 3: Beta (Week 3)

**Objective**: Test with 50% of users

**Duration**: 7 days

**Configuration**:
```bash
USE_UNIFIED_INTENT_ANALYZER=true
UNIFIED_INTENT_ROLLOUT_PHASE=beta
UNIFIED_INTENT_TRAFFIC_PERCENTAGE=50
```

**Test Scenarios**: Same as Phase 2, plus:

1. **Conversation Context**
   - User: "Che tempo fa?"
   - System: "In quale città?"
   - User: "A Roma"
   - Expected: Should understand context and classify correctly

2. **Repeated Queries**
   - Same query sent multiple times
   - Expected: Cache hit rate > 40%

3. **Performance Under Load**
   - Simulate 100 concurrent users
   - Expected: Throughput > 100 queries/sec

**Metrics to Collect**: Same as Phase 2, plus:
- Concurrent user handling
- Cache effectiveness
- User feedback

**Success Criteria**: Same as Phase 2, plus:
- Cache hit rate > 40%
- Throughput > 100 queries/sec
- Positive user feedback

**Rollback Trigger**: Same as Phase 2

### Phase 4: Production (Week 4+)

**Objective**: Full production deployment

**Duration**: 14+ days

**Configuration**:
```bash
USE_UNIFIED_INTENT_ANALYZER=true
UNIFIED_INTENT_ROLLOUT_PHASE=production
UNIFIED_INTENT_TRAFFIC_PERCENTAGE=100
```

**Test Scenarios**: Same as Phase 3

**Metrics to Collect**: Same as Phase 3

**Success Criteria**:
- All Phase 3 criteria met
- Stable for 14 days
- All SLOs achieved
- Ready to remove feature flag

## Test Execution

### Daily Testing Checklist

- [ ] Run full test suite (70 tests)
- [ ] Check monitoring dashboard
- [ ] Review error logs
- [ ] Collect user feedback
- [ ] Compare metrics with baseline
- [ ] Document any issues

### Weekly Review

- [ ] Analyze metrics trends
- [ ] Review user feedback
- [ ] Identify optimization opportunities
- [ ] Plan next phase

### Test Queries

#### Weather Queries (Italian)
```
Che tempo fa a Caltanissetta?
Che tempo fa a Roma?
Che tempo fa a Milano?
Piove oggi?
Qual è la temperatura a Palermo?
Domani pioverà?
```

#### Weather Queries (English)
```
What's the weather in New York?
What's the weather in London?
Show me the weather in Paris
Temperature in Tokyo
Will it rain tomorrow?
Current weather in Sydney
```

#### Conversational Queries (Italian)
```
Ciao, come stai?
Grazie mille
Arrivederci
Mi piace molto
Non mi piace
Che bello!
```

#### Conversational Queries (English)
```
Hello, how are you?
Thank you very much
Goodbye
I like it
I don't like it
That's great!
```

#### Price Queries
```
Qual è il prezzo dell'oro?
What's the price of Bitcoin?
Prezzo dell'argento
Price of oil
Quotazione euro/dollaro
EUR/USD exchange rate
```

#### Search Queries
```
Cerca ristoranti a Roma
Find hotels in Paris
Cerca farmacie a Milano
Search for museums in London
Dove posso trovare una pizzeria?
Where can I find a coffee shop?
```

#### Multi-Domain Queries
```
Che tempo fa a Roma e qual è il prezzo dell'oro?
Show me weather in Paris and search for restaurants
Che tempo fa a Milano e cerca pizzerie
What's the weather in London and find hotels
```

## Monitoring and Alerts

### Key Metrics

1. **Accuracy**
   - Weather: target ≥ 95%
   - Conversational: target ≥ 98%
   - Multi-domain: target ≥ 85%

2. **Performance**
   - p50 latency: target 100ms
   - p95 latency: target 200ms
   - p99 latency: target 250ms
   - Throughput: target 100 queries/sec

3. **Reliability**
   - Error rate: target < 1%
   - Cache hit rate: target > 40%
   - Uptime: target > 99.9%

### Alert Thresholds

- **Critical**: Accuracy < 90%, Error rate > 2%, p95 latency > 300ms
- **Warning**: Accuracy < 95%, Error rate > 1%, p95 latency > 250ms
- **Info**: Accuracy < 98%, Cache hit rate < 30%

### Monitoring Commands

```bash
# Start monitoring dashboard
python scripts/monitor_intent.py

# Check specific metrics
python -c "
from me4brain.engine.intent_monitoring import get_intent_monitor
monitor = get_intent_monitor()
metrics = monitor.get_metrics()
print(f'Accuracy: {metrics[\"overall_accuracy\"]:.1%}')
print(f'Error rate: {metrics[\"error_rate\"]:.1%}')
print(f'Avg latency: {metrics[\"avg_latency_ms\"]:.1f}ms')
"

# Check cache statistics
python -c "
from me4brain.engine.intent_cache import get_intent_cache
cache = get_intent_cache()
stats = cache.get_stats()
print(f'Hit rate: {stats.hit_rate:.1%}')
print(f'Size: {stats.size} entries')
"
```

## Issue Tracking

### Template for Reporting Issues

```
**Query**: [exact query that failed]
**Expected Classification**: [what should have happened]
**Actual Classification**: [what actually happened]
**Timestamp**: [when it happened]
**User**: [user ID if available]
**Phase**: [which phase]
**Severity**: [critical/high/medium/low]
```

### Example Issues

```
**Query**: "Che tempo fa a Caltanissetta?"
**Expected Classification**: TOOL_REQUIRED + geo_weather
**Actual Classification**: CONVERSATIONAL
**Timestamp**: 2024-03-10 14:30:00
**User**: user_123
**Phase**: Canary (10%)
**Severity**: Critical
```

## Success Criteria Summary

### Phase 1 (Disabled)
- ✓ System stable for 7 days
- ✓ Error rate < 1%
- ✓ Baseline metrics established

### Phase 2 (Canary 10%)
- ✓ Weather accuracy ≥ 95%
- ✓ Conversational accuracy ≥ 98%
- ✓ p95 latency < 200ms
- ✓ Error rate < 1%
- ✓ No user complaints

### Phase 3 (Beta 50%)
- ✓ All Phase 2 criteria met
- ✓ Cache hit rate > 40%
- ✓ Throughput > 100 queries/sec
- ✓ Positive user feedback

### Phase 4 (Production 100%)
- ✓ All Phase 3 criteria met
- ✓ Stable for 14 days
- ✓ All SLOs achieved

## Rollback Procedures

### Quick Rollback

```bash
# Option 1: Disable feature flag
export USE_UNIFIED_INTENT_ANALYZER=false

# Option 2: Reduce traffic
export UNIFIED_INTENT_TRAFFIC_PERCENTAGE=0

# Option 3: Switch to disabled phase
export UNIFIED_INTENT_ROLLOUT_PHASE=disabled

# Restart application
```

### Full Rollback

```bash
# Restore previous .env
cp .env.backup.TIMESTAMP .env

# Restart application
# System will use old ConversationalDetector
```

## Next Steps

1. **Week 1**: Deploy Phase 1, establish baseline
2. **Week 2**: Deploy Phase 2, monitor canary
3. **Week 3**: Deploy Phase 3, collect feedback
4. **Week 4+**: Deploy Phase 4, monitor production
5. **After 2 weeks**: Remove feature flag

## Support

For issues or questions:
1. Check DEPLOYMENT_REALWORLD.md
2. Review RUNBOOK.md
3. Check monitoring dashboard
4. Contact development team
