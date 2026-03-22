# 🚀 DEPLOYMENT EXECUTION: Phase 1 (Disabled)

**Status**: IN PROGRESS
**Date**: March 10, 2024
**Phase**: 1 - Disabled (0% Traffic)
**Duration**: 7 days

---

## Pre-Deployment Verification

### Step 1: Verify All Tests Pass ✅

```bash
cd Me4BrAIn
python -m pytest tests/engine/test_unified_intent_analyzer.py -v
python -m pytest tests/engine/test_unified_intent_properties.py -v
python -m pytest tests/engine/test_unified_intent_integration.py -v
python -m pytest tests/engine/test_feature_flags.py -v
python -m pytest tests/engine/test_intent_cache.py -v
```

**Expected Result**: 70 tests passing ✅

### Step 2: Verify Configuration

```bash
# Check that .env has these settings
grep "USE_UNIFIED_INTENT_ANALYZER" .env
grep "UNIFIED_INTENT_ROLLOUT_PHASE" .env
grep "UNIFIED_INTENT_TRAFFIC_PERCENTAGE" .env
```

**Expected Result**: All variables present

### Step 3: Verify Code Integration

```bash
# Check that UnifiedIntentAnalyzer is imported in core.py
grep -n "unified_intent_analyzer" src/me4brain/engine/core.py
```

**Expected Result**: Import found

---

## Phase 1 Deployment Steps

### Step 1: Configure Environment Variables

Update `.env` file with:

```bash
# Feature Flag Configuration
USE_UNIFIED_INTENT_ANALYZER=true
UNIFIED_INTENT_ROLLOUT_PHASE=disabled
UNIFIED_INTENT_TRAFFIC_PERCENTAGE=0

# Intent Analysis Configuration
INTENT_ANALYSIS_TIMEOUT=5.0
INTENT_ANALYSIS_MODEL=model_routing
INTENT_CACHE_TTL=300

# Cache Configuration
INTENT_CACHE_MAX_SIZE=10000

# Batch Processing
INTENT_BATCH_SIZE=10
INTENT_BATCH_TIMEOUT_MS=100
```

### Step 2: Deploy to Production

```bash
# 1. Backup current configuration
cp .env .env.backup.$(date +%s)

# 2. Update .env with new configuration
# (Use your deployment process)

# 3. Deploy code to production
# (Use your deployment process)

# 4. Restart application
# (Use your deployment process)
```

### Step 3: Verify Deployment

```bash
# Check that feature flag is disabled
python -c "
from me4brain.llm.config import get_llm_config
from me4brain.engine.feature_flags import get_feature_flag_manager

config = get_llm_config()
ffm = get_feature_flag_manager()

print(f'Feature enabled: {config.use_unified_intent_analyzer}')
print(f'Rollout phase: {ffm.current_phase}')
print(f'Traffic percentage: {ffm.traffic_percentage}%')
"
```

**Expected Result**:
```
Feature enabled: True
Rollout phase: RolloutPhase.DISABLED
Traffic percentage: 0%
```

### Step 4: Start Monitoring

```bash
# Terminal 1: Start monitoring dashboard
python scripts/monitor_intent.py

# Terminal 2: Check logs
tail -f logs/me4brain.log

# Terminal 3: Monitor metrics every hour
watch -n 3600 'python -c "
from me4brain.engine.intent_monitoring import get_intent_monitor
monitor = get_intent_monitor()
print(monitor.get_metrics())
"'
```

---

## Phase 1 Monitoring (7 Days)

### Daily Checklist

- [ ] Check monitoring dashboard
- [ ] Review error logs
- [ ] Verify no user complaints
- [ ] Document any issues
- [ ] Check system stability

### Metrics to Track

**Accuracy**:
- Weather queries: Should be routed to old system
- Conversational queries: Should be routed to old system
- Multi-domain queries: Should be routed to old system

**Performance**:
- p50 latency: Baseline
- p95 latency: Baseline
- p99 latency: Baseline
- Throughput: Baseline

**Reliability**:
- Error rate: Should be < 1%
- Uptime: Should be > 99.9%
- No user complaints

### Monitoring Commands

```bash
# Check current metrics
python -c "
from me4brain.engine.intent_monitoring import get_intent_monitor
monitor = get_intent_monitor()
metrics = monitor.get_metrics()
print(f'Total queries: {metrics.get(\"total_queries\", 0)}')
print(f'Error rate: {metrics.get(\"error_rate\", 0):.1%}')
print(f'Avg latency: {metrics.get(\"avg_latency_ms\", 0):.1f}ms')
"

# Check cache statistics
python -c "
from me4brain.engine.intent_cache import get_intent_cache
cache = get_intent_cache()
stats = cache.get_stats()
print(f'Cache size: {stats.size}')
print(f'Hit rate: {stats.hit_rate:.1%}')
"

# Check feature flag status
python -c "
from me4brain.engine.feature_flags import get_feature_flag_manager
ffm = get_feature_flag_manager()
print(f'Phase: {ffm.current_phase}')
print(f'Traffic: {ffm.traffic_percentage}%')
"
```

---

## Phase 1 Success Criteria

### ✅ System Stability
- [ ] System stable for 7 days
- [ ] No crashes or errors
- [ ] All services running

### ✅ Error Rate
- [ ] Error rate < 1%
- [ ] No critical errors
- [ ] All errors logged

### ✅ User Experience
- [ ] No user complaints
- [ ] No support tickets
- [ ] System responsive

### ✅ Baseline Metrics
- [ ] Baseline latency recorded
- [ ] Baseline throughput recorded
- [ ] Baseline accuracy recorded

---

## Phase 1 Daily Report Template

```
Date: [DATE]
Day: [1-7]

SYSTEM STATUS:
- Uptime: [%]
- Error rate: [%]
- User complaints: [0/N]

PERFORMANCE:
- p50 latency: [Xms]
- p95 latency: [Xms]
- p99 latency: [Xms]
- Throughput: [X q/s]

CACHE:
- Hit rate: [%]
- Size: [X entries]
- Avg latency: [Xms]

ISSUES:
- [List any issues]

NOTES:
- [Any observations]
```

---

## Phase 1 Completion Checklist

### Day 7 Review

- [ ] System stable for 7 days
- [ ] Error rate < 1%
- [ ] No user complaints
- [ ] Baseline metrics recorded
- [ ] All success criteria met
- [ ] Ready for Phase 2

### Approval

- [ ] Development Team: Approved
- [ ] QA Team: Approved
- [ ] DevOps Team: Approved
- [ ] Product Team: Approved

---

## Transition to Phase 2

Once Phase 1 is complete and all success criteria are met:

### Update Configuration

```bash
# Update .env for Phase 2
export UNIFIED_INTENT_ROLLOUT_PHASE=canary
export UNIFIED_INTENT_TRAFFIC_PERCENTAGE=10

# Restart application
```

### Verify Phase 2 Configuration

```bash
python -c "
from me4brain.engine.feature_flags import get_feature_flag_manager
ffm = get_feature_flag_manager()
print(f'Phase: {ffm.current_phase}')
print(f'Traffic: {ffm.traffic_percentage}%')
"
```

**Expected Result**:
```
Phase: RolloutPhase.CANARY
Traffic: 10%
```

---

## Rollback Procedure (If Needed)

### Quick Rollback

```bash
# Option 1: Disable feature flag
export USE_UNIFIED_INTENT_ANALYZER=false

# Option 2: Reduce traffic to 0%
export UNIFIED_INTENT_TRAFFIC_PERCENTAGE=0

# Option 3: Switch to disabled phase
export UNIFIED_INTENT_ROLLOUT_PHASE=disabled

# Restart application
```

### Verify Rollback

```bash
python -c "
from me4brain.llm.config import get_llm_config
config = get_llm_config()
print(f'Feature enabled: {config.use_unified_intent_analyzer}')
"
```

**Expected Result**: System uses old ConversationalDetector

---

## Support Contacts

### For Deployment Issues
→ Contact DevOps Team
→ Check [docs/DEPLOYMENT_REALWORLD.md](./docs/DEPLOYMENT_REALWORLD.md)

### For Monitoring Issues
→ Contact Development Team
→ Check [docs/MONITORING.md](./docs/MONITORING.md)

### For Performance Issues
→ Contact Development Team
→ Check [docs/PERFORMANCE.md](./docs/PERFORMANCE.md)

### For Troubleshooting
→ Check [docs/RUNBOOK.md](./docs/RUNBOOK.md)

---

## Timeline

### Day 1 (Today)
- [ ] Deploy Phase 1 (disabled)
- [ ] Verify deployment
- [ ] Start monitoring
- [ ] Establish baseline

### Days 2-6
- [ ] Monitor daily
- [ ] Check metrics
- [ ] Document issues
- [ ] Verify stability

### Day 7
- [ ] Final review
- [ ] Approve Phase 2
- [ ] Prepare transition

---

## Next Steps

1. **Now**: Run pre-deployment verification
2. **Today**: Deploy Phase 1 (disabled)
3. **Today**: Start monitoring dashboard
4. **Days 1-7**: Monitor and collect baseline metrics
5. **Day 7**: Review and approve Phase 2
6. **Day 8**: Deploy Phase 2 (10% traffic)

---

**Status**: READY FOR PHASE 1 DEPLOYMENT

**Next Step**: Execute pre-deployment verification and deploy Phase 1

---

**Prepared by**: Development Team
**Date**: March 10, 2024
**Status**: READY FOR EXECUTION
