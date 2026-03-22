# Runbook: UnifiedIntentAnalyzer Operations

## Quick Reference

### Enable Feature Flag

```bash
# Canary (10%)
export UNIFIED_INTENT_ROLLOUT_PHASE=canary
export UNIFIED_INTENT_TRAFFIC_PERCENTAGE=10

# Beta (50%)
export UNIFIED_INTENT_ROLLOUT_PHASE=beta
export UNIFIED_INTENT_TRAFFIC_PERCENTAGE=50

# Production (100%)
export UNIFIED_INTENT_ROLLOUT_PHASE=production
export UNIFIED_INTENT_TRAFFIC_PERCENTAGE=100
```

### Disable Feature Flag

```bash
export UNIFIED_INTENT_ROLLOUT_PHASE=disabled
export UNIFIED_INTENT_TRAFFIC_PERCENTAGE=0
```

### Check Status

```bash
# Check current phase
curl http://localhost:8000/api/feature-flags/status

# Check metrics
curl http://localhost:8000/api/metrics/intent

# Check cache stats
curl http://localhost:8000/api/cache/stats
```

## Common Issues and Solutions

### Issue 1: High Latency (p95 > 200ms)

**Symptoms**:
- Latency alerts firing
- Users reporting slow responses
- p95 latency > 200ms

**Diagnosis**:
```bash
# Check LLM API status
curl https://nano-gpt.com/api/v1/health

# Check cache hit rate
curl http://localhost:8000/api/cache/stats

# Check error rate
curl http://localhost:8000/api/metrics/intent
```

**Solutions**:

1. **LLM API Slow**:
   - Check LLM provider status
   - Increase timeout
   - Switch to faster model

2. **Cache Not Working**:
   - Check cache size
   - Verify cache enabled
   - Clear cache if corrupted

3. **Network Issues**:
   - Check network connectivity
   - Increase connection pool
   - Enable connection pooling

**Action**:
```bash
# Increase timeout
export INTENT_ANALYSIS_TIMEOUT=10

# Use faster model
export INTENT_ANALYSIS_MODEL=mistral-small

# Clear cache
curl -X POST http://localhost:8000/api/cache/clear
```

### Issue 2: Low Accuracy (< 90%)

**Symptoms**:
- Accuracy alerts firing
- Misclassification reports
- Accuracy < 90%

**Diagnosis**:
```bash
# Check misclassified queries
curl http://localhost:8000/api/metrics/misclassified

# Check confidence scores
curl http://localhost:8000/api/metrics/confidence

# Review logs
tail -f logs/intent_analysis.log | grep "low_confidence"
```

**Solutions**:

1. **Model Not Suitable**:
   - Switch to better model
   - Use GPT-4 for higher accuracy

2. **Prompt Needs Tuning**:
   - Review misclassified queries
   - Update prompt
   - Re-test

3. **Edge Cases**:
   - Add examples to prompt
   - Increase confidence threshold
   - Manual review

**Action**:
```bash
# Use better model
export INTENT_ANALYSIS_MODEL=gpt-4

# Increase confidence threshold
export INTENT_CONFIDENCE_THRESHOLD=0.8

# Review misclassified queries
curl http://localhost:8000/api/metrics/misclassified | head -20
```

### Issue 3: High Error Rate (> 1%)

**Symptoms**:
- Error rate alerts firing
- Errors in logs
- Error rate > 1%

**Diagnosis**:
```bash
# Check error types
curl http://localhost:8000/api/metrics/errors

# Check LLM API failures
curl http://localhost:8000/api/metrics/llm-failures

# Check JSON parse failures
curl http://localhost:8000/api/metrics/json-failures
```

**Solutions**:

1. **LLM API Failures**:
   - Check LLM provider status
   - Increase retry count
   - Enable fallback

2. **JSON Parse Failures**:
   - Check LLM response format
   - Improve response validation
   - Update prompt

3. **Validation Failures**:
   - Check input validation
   - Improve error handling
   - Add logging

**Action**:
```bash
# Increase retry count
export LLM_MAX_RETRIES=5

# Enable fallback
export INTENT_FALLBACK_ENABLED=true

# Check error logs
tail -f logs/intent_analysis.log | grep "error"
```

### Issue 4: Cache Not Working

**Symptoms**:
- Cache hit rate < 10%
- Cache size not growing
- No performance improvement

**Diagnosis**:
```bash
# Check cache stats
curl http://localhost:8000/api/cache/stats

# Check cache size
curl http://localhost:8000/api/cache/size

# Check cache hits
curl http://localhost:8000/api/cache/hits
```

**Solutions**:

1. **Cache Disabled**:
   - Enable cache in config
   - Verify cache initialized

2. **Cache Too Small**:
   - Increase max size
   - Reduce TTL

3. **Cache Corrupted**:
   - Clear cache
   - Restart service

**Action**:
```bash
# Enable cache
export INTENT_CACHE_ENABLED=true

# Increase cache size
export INTENT_CACHE_MAX_SIZE=20000

# Clear cache
curl -X POST http://localhost:8000/api/cache/clear

# Restart service
systemctl restart me4brain
```

## Monitoring

### Key Metrics to Watch

1. **Latency**:
   - p50: Should be ~110ms
   - p95: Should be < 200ms
   - p99: Should be < 250ms

2. **Accuracy**:
   - Weather: Should be ≥ 95%
   - Conversational: Should be ≥ 98%
   - Multi-domain: Should be ≥ 90%

3. **Error Rate**:
   - Should be < 1%
   - Alert if > 5%

4. **Cache Hit Rate**:
   - Should be > 30%
   - Alert if < 20%

### Dashboards

- **Overview**: Query volume, latency, accuracy, error rate
- **Latency**: p50, p95, p99 over time
- **Accuracy**: By query type over time
- **Errors**: Error types and frequency
- **Cache**: Hit rate, size, evictions

### Alerts

| Alert | Threshold | Action |
|-------|-----------|--------|
| High Latency | p95 > 200ms | Check LLM API, enable cache |
| Low Accuracy | < 90% | Review misclassified, update prompt |
| High Error Rate | > 1% | Check logs, increase retries |
| Low Cache Hit | < 20% | Check cache, increase size |
| LLM Failures | > 10% | Check LLM provider, enable fallback |

## Escalation

### Level 1: On-Call Engineer

- Monitor metrics
- Check logs
- Apply quick fixes
- Document issues

### Level 2: Engineering Lead

- Investigate root cause
- Plan fix
- Coordinate deployment
- Update team

### Level 3: VP Engineering

- Approve major changes
- Communicate with customers
- Plan long-term fixes
- Review lessons learned

## Rollback Procedure

### Quick Rollback

```bash
# Disable feature flag
export UNIFIED_INTENT_ROLLOUT_PHASE=disabled

# Verify rollback
curl http://localhost:8000/api/feature-flags/status

# Check metrics
curl http://localhost:8000/api/metrics/intent
```

### Full Rollback

```bash
# Stop new system
systemctl stop me4brain-unified-intent

# Restart old system
systemctl start me4brain-conversational-detector

# Verify old system working
curl http://localhost:8000/api/health

# Collect logs
tar -czf logs-$(date +%Y%m%d-%H%M%S).tar.gz logs/
```

### Post-Rollback

1. Collect logs and metrics
2. Identify root cause
3. Fix issues
4. Re-test in staging
5. Plan re-deployment

## Maintenance

### Daily Tasks

- [ ] Check metrics dashboard
- [ ] Review error logs
- [ ] Verify cache working
- [ ] Check LLM API status

### Weekly Tasks

- [ ] Review accuracy metrics
- [ ] Analyze misclassified queries
- [ ] Check cache effectiveness
- [ ] Review performance trends

### Monthly Tasks

- [ ] Optimize prompt
- [ ] Update model if needed
- [ ] Review and update runbook
- [ ] Plan improvements

## Contact Information

### On-Call

- **Primary**: [Name] - [Phone]
- **Secondary**: [Name] - [Phone]
- **Escalation**: [Manager] - [Phone]

### External Contacts

- **LLM Provider**: support@nano-gpt.com
- **Monitoring**: [Monitoring Team]
- **Infrastructure**: [Infra Team]

## See Also

- [Gradual Rollout Guide](./GRADUAL_ROLLOUT.md)
- [Performance Optimization](./PERFORMANCE_OPTIMIZATION.md)
- [Monitoring Guide](./MONITORING.md)
- [Deployment Checklist](./DEPLOYMENT_CHECKLIST.md)
