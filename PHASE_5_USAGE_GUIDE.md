# Phase 5: Prometheus Metrics & Diagnostics - Usage Guide

## Overview

Phase 5 adds comprehensive observability to the JAI Hybrid Routing system with:

1. **8 Prometheus metrics** for tracking classification performance
2. **Diagnostics endpoint** for real-time LLM provider health
3. **Instrumentation** of domain classifier with timing and error tracking
4. **Production-ready monitoring** setup

## Accessing the Diagnostics Endpoint

### Get LLM Chain Status

```bash
curl http://localhost:8089/v1/diagnostics/llm-chain
```

### Response Format

```json
{
  "config": {
    "model_routing": "llama2",
    "model_primary": "ollama",
    "llm_local_only": true,
    "ollama_base_url": "http://localhost:11434",
    "lmstudio_base_url": "http://localhost:1234"
  },
  "health": {
    "ollama": {
      "healthy": true,
      "error": null,
      "latency_ms": 45,
      "models": ["llama2:latest", "neural-chat:latest"]
    },
    "lmstudio": {
      "healthy": false,
      "error": "Connection refused",
      "latency_ms": null
    }
  },
  "resolution": {
    "ok": true,
    "client": "NanoGPTClient",
    "model": "llama2:latest",
    "error": null
  },
  "recommendation": "✅ OK: Ollama is healthy and ready with model 'llama2'"
}
```

### Status Indicators

- **✅ OK**: Ollama is healthy and ready
- **⚠️ DEGRADED**: Ollama down, LM Studio fallback active
- **🔴 CRITICAL**: No local LLM available

## Prometheus Metrics

### Accessing Metrics

Prometheus metrics are automatically exposed at the `/metrics` endpoint (FastAPI default):

```bash
curl http://localhost:8089/metrics | grep domain_classification
```

### Available Metrics

#### 1. Classification Total (Counter)

Tracks total classifications by method and success:

```
domain_classification_total{method="llm",success="true"} 1250
domain_classification_total{method="llm",success="false"} 15
domain_classification_total{method="fallback_keyword",success="true"} 32
```

**Query examples** (Prometheus):
```
# Total successful LLM classifications
rate(domain_classification_total{method="llm",success="true"}[5m])

# Success rate of LLM classification
domain_classification_total{method="llm",success="true"} / domain_classification_total{method="llm"}
```

#### 2. Classification Latency (Histogram)

Latency in seconds by classification method:

```
domain_classification_latency_seconds_bucket{method="llm",le="0.1"} 450
domain_classification_latency_seconds_bucket{method="llm",le="0.5"} 980
domain_classification_latency_seconds_bucket{method="llm",le="1.0"} 1200
domain_classification_latency_seconds_bucket{method="llm",le="30.0"} 1250
domain_classification_latency_seconds_sum{method="llm"} 847.5
domain_classification_latency_seconds_count{method="llm"} 1250
```

**Query examples**:
```
# P95 latency for LLM classification
histogram_quantile(0.95, domain_classification_latency_seconds_bucket{method="llm"})

# Average latency
rate(domain_classification_latency_seconds_sum{method="llm"}[5m]) / rate(domain_classification_latency_seconds_count{method="llm"}[5m])
```

#### 3. LLM Errors (Counter)

Error types encountered:

```
domain_classification_llm_errors_total{error_type="timeout"} 8
domain_classification_llm_errors_total{error_type="connection"} 2
domain_classification_llm_errors_total{error_type="parse"} 3
domain_classification_llm_errors_total{error_type="validation"} 1
```

**Query examples**:
```
# Timeout error rate
rate(domain_classification_llm_errors_total{error_type="timeout"}[5m])

# All errors combined
sum(rate(domain_classification_llm_errors_total[5m]))
```

#### 4. Classification Confidence (Histogram)

Distribution of confidence scores:

```
domain_classification_confidence_bucket{method="llm",le="0.7"} 45
domain_classification_confidence_bucket{method="llm",le="0.8"} 120
domain_classification_confidence_bucket{method="llm",le="0.9"} 980
domain_classification_confidence_bucket{method="llm",le="1.0"} 1250
```

**Query examples**:
```
# Percentage of classifications with 90%+ confidence
100 * histogram_quantile(0.90, domain_classification_confidence_bucket{method="llm"})

# Low confidence classifications (< 0.7)
domain_classification_confidence_bucket{method="llm",le="0.7"}
```

#### 5. Retry Attempts (Counter)

Retry reasons:

```
domain_classification_retries_total{reason="timeout"} 8
domain_classification_retries_total{reason="error"} 5
domain_classification_retries_total{reason="low_confidence"} 2
```

#### 6. Query Context (Counter)

Queries with conversation history:

```
domain_classification_with_context_total{has_context="true"} 420
domain_classification_with_context_total{has_context="false"} 830
```

**Query examples**:
```
# Percentage of queries with context
100 * domain_classification_with_context_total{has_context="true"} / (domain_classification_with_context_total{has_context="true"} + domain_classification_with_context_total{has_context="false"})
```

#### 7. Degradation Level (Gauge)

Current degradation level (0-3):

```
domain_classification_degradation_level{query_type="general"} 0
domain_classification_degradation_level{query_type="complex"} 1
```

**Levels**:
- 0: FULL_LLM (normal operation)
- 1: SIMPLIFIED_LLM (complex prompt failed)
- 2: HYBRID (LLM uncertain, using keyword backup)
- 3: KEYWORD_ONLY (last resort)

#### 8. Degradation Transitions (Counter)

Transitions between levels:

```
domain_classification_degradation_transitions{from_level="0",to_level="1"} 12
domain_classification_degradation_transitions{from_level="1",to_level="2"} 3
domain_classification_degradation_transitions{from_level="2",to_level="3"} 1
```

## Grafana Dashboard Setup

### Create Dashboard

1. In Grafana, click **"+" → Create Dashboard**
2. Add new panels with these queries:

### Panel 1: LLM Classification Success Rate

```promql
sum(rate(domain_classification_total{method="llm",success="true"}[5m])) / sum(rate(domain_classification_total{method="llm"}[5m]))
```

**Panel Type**: Graph or Gauge
**Alert Threshold**: < 0.95 (95% success)

### Panel 2: Average Latency

```promql
rate(domain_classification_latency_seconds_sum{method="llm"}[5m]) / rate(domain_classification_latency_seconds_count{method="llm"}[5m])
```

**Panel Type**: Graph
**Alert Threshold**: > 5 seconds

### Panel 3: Error Rate by Type

```promql
sum by (error_type) (rate(domain_classification_llm_errors_total[5m]))
```

**Panel Type**: Pie chart

### Panel 4: Confidence Distribution

```promql
histogram_quantile(0.95, domain_classification_confidence_bucket{method="llm"})
```

**Panel Type**: Stat/Gauge
**Threshold**: > 0.85

## Alerting Rules (Prometheus)

Add to your `prometheus.yml`:

```yaml
rule_files:
  - 'rules/domain-classification.yml'
```

Create `rules/domain-classification.yml`:

```yaml
groups:
- name: domain_classification
  interval: 30s
  rules:
  
  # Alert: LLM classification success rate below 95%
  - alert: LLMClassificationSuccessRateLow
    expr: |
      sum(rate(domain_classification_total{method="llm",success="true"}[5m])) / 
      sum(rate(domain_classification_total{method="llm"}[5m])) < 0.95
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "LLM classification success rate below 95%"
      description: "Current rate: {{ $value | humanizePercentage }}"
  
  # Alert: High error rate
  - alert: HighLLMErrorRate
    expr: sum(rate(domain_classification_llm_errors_total[5m])) > 0.1
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "High LLM error rate"
      description: "{{ $value }} errors per second"
  
  # Alert: Timeout errors increasing
  - alert: TimeoutErrorsIncreasing
    expr: rate(domain_classification_llm_errors_total{error_type="timeout"}[5m]) > 0.05
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "LLM timeout rate increasing"
      description: "{{ $value }} timeouts per second"
  
  # Alert: Fallback usage high
  - alert: HighFallbackUsage
    expr: |
      sum(rate(domain_classification_total{method="fallback_keyword"}[5m])) / 
      (sum(rate(domain_classification_total{method="llm"}[5m])) + 
       sum(rate(domain_classification_total{method="fallback_keyword"}[5m]))) > 0.2
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "Fallback classification above 20%"
      description: "Current rate: {{ $value | humanizePercentage }}"
  
  # Alert: Degradation level elevated
  - alert: DegradationLevelHigh
    expr: domain_classification_degradation_level > 1
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "Domain classification degradation level elevated"
      description: "Current level: {{ $value }} (0=FULL_LLM, 3=KEYWORD_ONLY)"
```

## Testing Metrics

Run the test suite to verify metrics integration:

```bash
# Run Phase 5 tests
uv run pytest tests/unit/test_phase5_metrics_diagnostics.py -v

# Run all tests including Phase 4
uv run pytest tests/unit/test_model_resolution.py \
              tests/integration/test_domain_classifier.py \
              tests/e2e/test_full_query_flow.py \
              tests/unit/test_phase5_metrics_diagnostics.py -v
```

## Troubleshooting

### Metrics not appearing

1. Check Prometheus is scraping the endpoint:
   ```bash
   curl http://localhost:8089/metrics | grep domain_classification
   ```

2. Verify FastAPI app is running and `/metrics` is accessible

3. Check Prometheus `prometheus.yml` has correct target:
   ```yaml
   scrape_configs:
   - job_name: 'me4brain'
     static_configs:
     - targets: ['localhost:8089']
   ```

### Diagnostics endpoint returns 500

1. Check logs for import errors:
   ```bash
   grep -i "diagnostics\|llm_config\|health" <your-logs>
   ```

2. Verify LLM config is properly initialized:
   ```bash
   curl http://localhost:8089/v1/llm-config
   ```

3. Ensure health checker module is available:
   ```bash
   python -c "from me4brain.llm.health import get_llm_health_checker; print('OK')"
   ```

## Production Deployment

### Environment Setup

```bash
# Set LLM configuration
export OLLAMA_BASE_URL=http://ollama:11434
export LMSTUDIO_BASE_URL=http://lmstudio:1234
export LLM_MODEL_ROUTING=llama2

# Start Ollama
ollama serve &

# Start Me4BrAIn API
uv run me4brain
```

### Monitoring Stack

```yaml
# docker-compose.yml example
services:
  me4brain:
    ports:
      - "8089:8089"
    environment:
      OLLAMA_BASE_URL: http://ollama:11434
      LLM_MODEL_ROUTING: llama2

  prometheus:
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'

  grafana:
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
```

## Next Steps

1. **Set up Grafana dashboards** for visual monitoring
2. **Configure alerting rules** for SLO violations
3. **Enable metrics export** to external systems (CloudWatch, Datadog)
4. **Monitor Phase 1 fixes** to ensure no fallback cascade
5. **Establish baselines** for normal latency and error rates

---

For more information, see:
- `.workflow/PHASE_5_STATE.md` - Implementation details
- `.workflow/JAI_IMPLEMENTATION_PLAN.md` - Full plan
- `backend/src/me4brain/engine/hybrid_router/metrics.py` - Metric definitions
- `backend/src/me4brain/api/routes/diagnostics.py` - Endpoint implementation
