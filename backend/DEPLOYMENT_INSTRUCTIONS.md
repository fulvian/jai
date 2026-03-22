# Deployment Instructions: Unified Intent Analysis System

## Status: READY FOR PRODUCTION TESTING

---

## Pre-Deployment Verification

### 1. Run Full Test Suite
```bash
cd Me4BrAIn
python -m pytest tests/engine/test_unified_intent_analyzer.py -v
python -m pytest tests/engine/test_unified_intent_properties.py -v
python -m pytest tests/engine/test_unified_intent_integration.py -v
python -m pytest tests/engine/test_feature_flags.py -v
python -m pytest tests/engine/test_intent_cache.py -v
```

**Expected**: 70 tests passing ✅

### 2. Verify Configuration
```bash
# Check .env file has these settings
export USE_UNIFIED_INTENT_ANALYZER=true
export UNIFIED_INTENT_ROLLOUT_PHASE=disabled
export UNIFIED_INTENT_TRAFFIC_PERCENTAGE=0
```

### 3. Verify Code Integration
```bash
# Check that UnifiedIntentAnalyzer is imported in core.py
grep -n "unified_intent_analyzer" src/me4brain/engine/core.py
```

---

## Phase 1: Disabled (Week 1)

### Deploy
```bash
# 1. Update .env
export USE_UNIFIED_INTENT_ANALYZER=true
export UNIFIED_INTENT_ROLLOUT_PHASE=disabled
export UNIFIED_INTENT_TRAFFIC_PERCENTAGE=0

# 2. Deploy to production
# (Use your deployment process)

# 3. Verify deployment
python -c "
from me4brain.llm.config import get_llm_config
config = get_llm_config()
print(f'Feature enabled: {config.use_unified_intent_analyzer}')
"
```

### Monitor
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

### Success Criteria
- System stable for 7 days
- Error rate < 1%
- No user complaints

---

## Phase 2: Canary (Week 2)

### Deploy
```bash
# Update .env
export UNIFIED_INTENT_ROLLOUT_PHASE=canary
export UNIFIED_INTENT_TRAFFIC_PERCENTAGE=10

# Restart application
```

### Test Queries
- Weather: "Che tempo fa a Caltanissetta?"
- Conversational: "Ciao, come stai?"
- Multi-domain: "Che tempo fa a Roma e qual è il prezzo dell'oro?"

### Monitor
- Weather accuracy ≥ 95%
- Conversational accuracy ≥ 98%
- p95 latency < 200ms
- Error rate < 1%

### Success Criteria
- All metrics met
- No user complaints
- Positive feedback

---

## Phase 3: Beta (Week 3)

### Deploy
```bash
# Update .env
export UNIFIED_INTENT_ROLLOUT_PHASE=beta
export UNIFIED_INTENT_TRAFFIC_PERCENTAGE=50

# Restart application
```

### Monitor
- Cache hit rate > 40%
- Throughput > 100 queries/sec
- All Phase 2 criteria still met

### Success Criteria
- All Phase 2 criteria met
- Positive user feedback
- Performance targets met

---

## Phase 4: Production (Week 4+)

### Deploy
```bash
# Update .env
export UNIFIED_INTENT_ROLLOUT_PHASE=production
export UNIFIED_INTENT_TRAFFIC_PERCENTAGE=100

# Restart application
```

### Monitor
- Monitor for 2 weeks
- Verify all SLOs met
- Collect final metrics

### Success Criteria
- All Phase 3 criteria met
- Stable for 14 days
- Ready to remove feature flag

---

## Rollback Procedure

### Quick Rollback (2 minutes)
```bash
# Option 1: Disable feature flag
export USE_UNIFIED_INTENT_ANALYZER=false

# Option 2: Reduce traffic
export UNIFIED_INTENT_TRAFFIC_PERCENTAGE=0

# Option 3: Switch to disabled phase
export UNIFIED_INTENT_ROLLOUT_PHASE=disabled

# Restart application
```

---

## Monitoring Commands

### Real-Time Dashboard
```bash
python scripts/monitor_intent.py
```

### Check Metrics
```bash
python -c "
from me4brain.engine.intent_monitoring import get_intent_monitor
monitor = get_intent_monitor()
print(monitor.get_metrics())
"
```

### Check Cache
```bash
python -c "
from me4brain.engine.intent_cache import get_intent_cache
cache = get_intent_cache()
print(cache.get_stats())
"
```

---

## Documentation References

- [START_HERE.md](./START_HERE.md) - Quick start
- [DEPLOYMENT_READY.md](./DEPLOYMENT_READY.md) - Checklist
- [docs/DEPLOYMENT_REALWORLD.md](./docs/DEPLOYMENT_REALWORLD.md) - Detailed guide
- [docs/REALWORLD_TEST_PLAN.md](./docs/REALWORLD_TEST_PLAN.md) - Test strategy
- [docs/RUNBOOK.md](./docs/RUNBOOK.md) - Troubleshooting

---

**Status**: ✅ READY FOR DEPLOYMENT

**Next Step**: Deploy Phase 1 (Disabled) to production
