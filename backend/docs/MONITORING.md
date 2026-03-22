# Intent Analysis Monitoring and Observability

## Overview

The UnifiedIntentAnalyzer includes comprehensive monitoring and observability infrastructure for production deployments. This guide covers metrics collection, structured logging, dashboards, and alerting.

## Metrics Collection

### IntentMonitor

The `IntentMonitor` class collects metrics for all intent analysis operations:

```python
from me4brain.engine.intent_monitoring import get_intent_monitor

monitor = get_intent_monitor()

# Get current metrics
metrics = monitor.get_metrics()
print(metrics.to_dict())
```

### Available Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `total_queries` | Counter | Total queries analyzed |
| `conversational_queries` | Counter | Conversational queries |
| `tool_required_queries` | Counter | Tool-required queries |
| `failed_queries` | Counter | Failed classifications |
| `avg_latency_ms` | Gauge | Average latency (ms) |
| `min_latency_ms` | Gauge | Minimum latency (ms) |
| `max_latency_ms` | Gauge | Maximum latency (ms) |
| `avg_confidence` | Gauge | Average confidence score |
| `low_confidence_queries` | Counter | Queries with confidence < 0.7 |
| `cache_hit_rate` | Gauge | Cache hit rate (0.0-1.0) |
| `error_rate` | Gauge | Error rate (0.0-1.0) |
| `accuracy` | Gauge | Classification accuracy (if labeled) |
| `domain_distribution` | Histogram | Distribution of domains |
| `complexity_distribution` | Histogram | Distribution of complexity levels |
| `llm_api_failures` | Counter | LLM API failures |
| `json_parse_failures` | Counter | JSON parse failures |
| `invalid_domain_filters` | Counter | Invalid domain filters |

## Structured Logging

All intent analysis operations are logged with structured data:

```python
# Example log output
{
    "event": "intent_analyzed",
    "query_preview": "Che tempo fa?",
    "intent": "tool_required",
    "domains": ["geo_weather"],
    "complexity": "simple",
    "confidence": 0.95,
    "latency_ms": 125.5
}
```

### Log Events

| Event | Fields | Description |
|-------|--------|-------------|
| `intent_analyzed` | intent, domains, complexity, confidence, latency_ms | Successful classification |
| `intent_analysis_failed` | error, error_type, query_preview | Classification failure |
| `intent_analysis_json_parse_failed` | error, response_preview | JSON parsing error |
| `intent_analysis_validation_failed` | error, query_preview | Validation error |
| `empty_query_received` | - | Empty query provided |
| `query_truncated` | original_length, truncated_length | Query truncated |

## Monitoring Dashboard

### Prometheus Metrics

Export metrics to Prometheus:

```python
from prometheus_client import Counter, Histogram, Gauge
from me4brain.engine.intent_monitoring import get_intent_monitor

monitor = get_intent_monitor()

# Create Prometheus metrics
intent_queries = Counter(
    'intent_queries_total',
    'Total intent analysis queries',
    ['intent_type']
)

intent_latency = Histogram(
    'intent_latency_ms',
    'Intent analysis latency in milliseconds',
    buckets=[50, 100, 150, 200, 300, 500]
)

intent_confidence = Gauge(
    'intent_confidence_avg',
    'Average confidence score'
)

# Update metrics periodically
def update_prometheus_metrics():
    metrics = monitor.get_metrics()
    intent_queries.labels(intent_type='conversational').inc(
        metrics.conversational_queries
    )
    intent_queries.labels(intent_type='tool_required').inc(
        metrics.tool_required_queries
    )
    intent_latency.observe(metrics.avg_latency_ms)
    intent_confidence.set(metrics.avg_confidence)
```

### Grafana Dashboard

Create a Grafana dashboard with these panels:

**Panel 1: Query Volume**
```
SELECT rate(intent_queries_total[5m]) FROM prometheus
```

**Panel 2: Latency (p95)**
```
SELECT histogram_quantile(0.95, intent_latency_ms) FROM prometheus
```

**Panel 3: Error Rate**
```
SELECT rate(intent_queries_failed[5m]) / rate(intent_queries_total[5m]) FROM prometheus
```

**Panel 4: Confidence Distribution**
```
SELECT intent_confidence_avg FROM prometheus
```

**Panel 5: Domain Distribution**
```
SELECT intent_domain_distribution FROM prometheus
```

**Panel 6: Cache Hit Rate**
```
SELECT intent_cache_hit_rate FROM prometheus
```

## Alerting

### Alert Rules

Set up alerts for these conditions:

#### Alert 1: High Error Rate

```yaml
alert: IntentAnalysisHighErrorRate
expr: rate(intent_queries_failed[5m]) / rate(intent_queries_total[5m]) > 0.05
for: 5m
annotations:
  summary: "Intent analysis error rate > 5%"
  description: "Error rate is {{ $value | humanizePercentage }}"
```

#### Alert 2: High Latency

```yaml
alert: IntentAnalysisHighLatency
expr: histogram_quantile(0.95, intent_latency_ms) > 300
for: 5m
annotations:
  summary: "Intent analysis p95 latency > 300ms"
  description: "Latency is {{ $value | humanize }}ms"
```

#### Alert 3: Low Confidence

```yaml
alert: IntentAnalysisLowConfidence
expr: (count(intent_confidence < 0.7) / count(intent_confidence)) > 0.1
for: 10m
annotations:
  summary: "Intent analysis low confidence rate > 10%"
  description: "Low confidence rate is {{ $value | humanizePercentage }}"
```

#### Alert 4: LLM API Failures

```yaml
alert: IntentAnalysisLLMFailures
expr: rate(intent_llm_api_failures[5m]) > 0.1
for: 5m
annotations:
  summary: "Intent analysis LLM API failures > 10%"
  description: "Failure rate is {{ $value | humanizePercentage }}"
```

### Alert Channels

Configure alert notifications:

- **Slack**: Send alerts to #me4brain-alerts
- **PagerDuty**: Critical alerts trigger on-call
- **Email**: Daily summary of metrics

## Performance Monitoring

### Latency SLO

**Target**: 95th percentile latency < 200ms

```python
monitor = get_intent_monitor()
metrics = monitor.get_metrics()

# Check SLO
if metrics.avg_latency_ms > 200:
    logger.warning("latency_slo_violated", latency_ms=metrics.avg_latency_ms)
```

### Accuracy SLO

**Target**: 95% accuracy for weather queries, 98% for conversational

```python
# Track accuracy with labeled data
monitor.record_classification_feedback(
    predicted_intent="tool_required",
    actual_intent="tool_required"  # From user feedback
)

metrics = monitor.get_metrics()
accuracy = metrics.accuracy
if accuracy < 0.95:
    logger.warning("accuracy_slo_violated", accuracy=accuracy)
```

### Error Rate SLO

**Target**: < 1% error rate

```python
metrics = monitor.get_metrics()
if metrics.error_rate > 0.01:
    logger.warning("error_rate_slo_violated", error_rate=metrics.error_rate)
```

## Observability Integration

### OpenTelemetry

Export metrics to OpenTelemetry:

```python
from opentelemetry import metrics
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider

# Create meter provider
reader = PrometheusMetricReader()
provider = MeterProvider(metric_readers=[reader])
metrics.set_meter_provider(provider)

# Create meter
meter = metrics.get_meter(__name__)

# Create instruments
intent_counter = meter.create_counter(
    "intent_queries",
    description="Intent analysis queries"
)

intent_histogram = meter.create_histogram(
    "intent_latency_ms",
    description="Intent analysis latency"
)

# Record metrics
intent_counter.add(1, {"intent": "tool_required"})
intent_histogram.record(125.5)
```

### Datadog Integration

Send metrics to Datadog:

```python
from datadog import initialize, api

options = {
    'api_key': 'YOUR_API_KEY',
    'app_key': 'YOUR_APP_KEY'
}

initialize(**options)

# Send metrics
monitor = get_intent_monitor()
metrics = monitor.get_metrics()

api.Metric.send(
    metric='intent.queries.total',
    points=metrics.total_queries,
    tags=['service:me4brain']
)

api.Metric.send(
    metric='intent.latency.avg',
    points=metrics.avg_latency_ms,
    tags=['service:me4brain']
)
```

## Debugging

### Enable Debug Logging

```python
import logging
import structlog

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
structlog.configure(
    processors=[
        structlog.processors.JSONRenderer()
    ]
)
```

### Inspect Metrics

```python
from me4brain.engine.intent_monitoring import get_intent_monitor

monitor = get_intent_monitor()

# Get metrics
metrics = monitor.get_metrics()

# Print metrics
print(f"Total queries: {metrics.total_queries}")
print(f"Avg latency: {metrics.avg_latency_ms:.2f}ms")
print(f"Error rate: {metrics.error_rate:.1%}")
print(f"Cache hit rate: {metrics.cache_hit_rate:.1%}")

# Check for alerts
alerts = monitor.check_alerts()
for alert in alerts:
    print(f"[{alert['severity']}] {alert['alert_type']}: {alert['message']}")
```

### Trace Analysis

Enable distributed tracing:

```python
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Create Jaeger exporter
jaeger_exporter = JaegerExporter(
    agent_host_name="localhost",
    agent_port=6831,
)

# Create tracer provider
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(jaeger_exporter)
)

# Get tracer
tracer = trace.get_tracer(__name__)

# Trace intent analysis
with tracer.start_as_current_span("intent_analysis") as span:
    analysis = await analyzer.analyze(query)
    span.set_attribute("intent", analysis.intent.value)
    span.set_attribute("confidence", analysis.confidence)
```

## Best Practices

1. **Monitor latency**: Track p50, p95, p99 latencies
2. **Track accuracy**: Collect user feedback to measure accuracy
3. **Alert on errors**: Set up alerts for high error rates
4. **Cache monitoring**: Track cache hit rates to optimize performance
5. **Domain analysis**: Monitor domain distribution to understand usage patterns
6. **Confidence tracking**: Monitor low confidence queries for potential issues
7. **Regular reviews**: Review metrics weekly to identify trends
8. **Capacity planning**: Use metrics to plan for scaling

## See Also

- [UnifiedIntentAnalyzer Guide](./unified-intent-analysis.md)
- [API Reference](./api/unified-intent-analyzer.md)
- [Performance Benchmarks](./PERFORMANCE.md)
