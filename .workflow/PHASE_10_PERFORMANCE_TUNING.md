# JAI - Phase 10 Performance Tuning Guide

**Version**: 1.0  
**Date**: 2026-03-22  
**Phase**: 10 - Production Deployment & Performance Optimization

---

## Overview

This guide provides comprehensive performance tuning recommendations for JAI production deployments. Target metrics:

| Metric | Target |
|--------|--------|
| P99 Latency | < 1.5s |
| Error Rate | < 0.5% |
| Cache Hit Ratio | > 30% |
| Availability | > 99.9% |

---

## 1. Application-Level Tuning

### 1.1 Python Performance

```python
# backend/src/me4brain/config/performance.py
from pydantic_settings import BaseSettings

class PerformanceSettings(BaseSettings):
    """Performance tuning configuration."""
    
    # Connection pool settings
    db_pool_size: int = 20
    db_max_overflow: int = 40
    db_pool_recycle: int = 3600
    
    # Redis connection pool
    redis_pool_size: int = 50
    redis_socket_timeout: int = 5
    
    # Worker settings
    uvicorn_workers: int = 4
    uvicorn_loop: str = "asyncio"
    
    # Request limits
    max_request_size: int = 10 * 1024 * 1024  # 10MB
    request_timeout: int = 30
```

### 1.2 Async Optimization

```python
# Use connection pooling for database
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=40,
    pool_recycle=3600,
    pool_pre_ping=True,  # Verify connections
    echo=False,
)

# Use async Redis
import aioredis
redis = await aioredis.from_url(
    REDIS_URL,
    max_connections=50,
    socket_timeout=5,
    socket_connect_timeout=5,
)
```

### 1.3 Response Compression

```python
# In FastAPI app
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

app = FastAPI()
app.add_middleware(GZipMiddleware, minimum_size=1000)
```

---

## 2. Database Optimization

### 2.1 PostgreSQL Configuration

```sql
-- postgresql.conf tuning

-- Memory settings (adjust based on available RAM)
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 64MB
maintenance_work_mem = 128MB

-- Connection settings
max_connections = 200
tcp_keepalives_idle = 60
tcp_keepalives_interval = 10
tcp_keepalives_count = 10

-- Write performance
wal_buffers = 16MB
checkpoint_completion_target = 0.9
max_wal_size = 2GB

-- Query planning
random_page_cost = 1.1
effective_io_concurrency = 200
```

### 2.2 Indexes

```sql
-- Add indexes for common queries
CREATE INDEX CONCURRENTLY idx_conversations_user_id 
    ON conversations(user_id, created_at DESC);

CREATE INDEX CONCURRENTLY idx_messages_conversation_id 
    ON messages(conversation_id, timestamp DESC);

CREATE INDEX CONCURRENTLY idx_audit_logs_user_timestamp 
    ON audit_logs(user_id, timestamp DESC);

-- Partial indexes for active data
CREATE INDEX CONCURRENTLY idx_conversations_active 
    ON conversations(user_id, updated_at DESC) 
    WHERE archived = FALSE;
```

### 2.3 Connection Pooling

```yaml
# kubernetes/deployment.yaml - add PgBouncer sidecar
- name: pgbouncer
  image: pgbouncer/pgbouncer:latest
  ports:
    - containerPort: 5432
  env:
    - name: DATABASE_URL
      valueFrom:
        secretKeyRef:
          name: me4brain-secrets
          key: DB_PASSWORD
  resources:
    limits:
      memory: 128Mi
      cpu: 250m
```

---

## 3. Caching Strategy

### 3.1 Redis Configuration

```conf
# redis.conf

# Memory
maxmemory 2gb
maxmemory-policy allkeys-lru

# Persistence
appendonly yes
appendfsync everysec

# Performance
tcp-backlog 511
timeout 30
tcp-keepalive 300
```

### 3.2 Cache Layers

| Layer | TTL | Description |
|-------|-----|-------------|
| Semantic Cache | 1 hour | Similar query results |
| Query Cache | 30 min | Exact query matches |
| Session Cache | 24 hours | User sessions |
| Config Cache | 1 hour | Application config |

### 3.3 Cache Implementation

```python
# backend/src/me4brain/cache/cache_manager.py
class CacheManager:
    """Multi-layer caching strategy."""
    
    SEMANTIC_TTL = 3600  # 1 hour
    QUERY_TTL = 1800      # 30 min
    SESSION_TTL = 86400   # 24 hours
    
    async def get_cached_response(self, query: str, model: str) -> Optional[dict]:
        # Try exact match first
        cache_key = self._generate_key(query, model)
        cached = await self.redis.get(cache_key)
        if cached:
            return json.loads(cached)
        
        # Try semantic match
        embedding = await self._get_embedding(query)
        similar = await self.semantic_cache.find_similar(embedding)
        if similar:
            return similar
        
        return None
```

---

## 4. LLM Optimization

### 4.1 Request Batching

```python
# Batch similar requests to reduce LLM calls
class RequestBatcher:
    def __init__(self, max_batch_size: int = 10, max_wait_ms: int = 100):
        self.queue: list[Request] = []
        self.max_batch_size = max_batch_size
        self.max_wait_ms = max_wait_ms
    
    async def add(self, request: Request) -> Response:
        self.queue.append(request)
        
        if len(self.queue) >= self.max_batch_size:
            return await self._flush()
        
        # Wait for timeout or max batch
        await asyncio.sleep(self.max_wait_ms / 1000)
        return await self._flush()
```

### 4.2 Timeout Configuration

```python
# LLM timeout settings
LLM_TIMEOUT = {
    "ollama": 30,      # Local LLM
    "lmstudio": 30,    # Local LLM
    "openai": 60,      # Cloud LLM
    "anthropic": 60,   # Cloud LLM
}

# Circuit breaker
CIRCUIT_BREAKER = {
    "failure_threshold": 5,
    "recovery_timeout": 60,
    "expected_exception": "LLMProviderError",
}
```

### 4.3 Fallback Chain

```python
# Try providers in order of preference and latency
FALLBACK_CHAIN = {
    "ollama": ["lmstudio", "openai", "anthropic"],
    "lmstudio": ["ollama", "openai", "anthropic"],
    "openai": ["anthropic"],
}
```

---

## 5. Kubernetes Resource Tuning

### 5.1 HPA Configuration

```yaml
# Already in kubernetes/deployment.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: me4brain-hpa
spec:
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 10
          periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Percent
          value: 100
          periodSeconds: 15
```

### 5.2 Resource Limits

```yaml
# Recommended production limits
resources:
  requests:
    memory: "512Mi"
    cpu: "250m"
  limits:
    memory: "2Gi"
    cpu: "2000m"
```

### 5.3 Pod Disruption Budget

```yaml
# Already configured
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: me4brain-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: me4brain
```

---

## 6. Monitoring & Benchmarks

### 6.1 Key Metrics

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| P50 Latency | < 200ms | > 500ms |
| P99 Latency | < 1500ms | > 2000ms |
| Error Rate | < 0.1% | > 0.5% |
| Cache Hit Ratio | > 30% | < 20% |
| DB Query Time | < 50ms | > 100ms |
| Redis Latency | < 5ms | > 10ms |

### 6.2 Benchmark Tests

```python
# tests/performance/test_latency_benchmarks.py
import pytest

@pytest.mark.benchmark
def test_classify_latency(benchmark):
    """Benchmark domain classification."""
    result = benchmark(domain_classifier.classify, "Python help")
    assert result.latency < 100  # ms

@pytest.mark.benchmark  
def test_cache_hit_latency(benchmark):
    """Benchmark cache hit."""
    cache.get("test_key")
    result = benchmark(cache.get, "test_key")
    assert result < 5  # ms

@pytest.mark.benchmark
def test_db_query_latency(benchmark):
    """Benchmark database query."""
    result = benchmark(session.execute, "SELECT * FROM conversations")
    assert result < 50  # ms
```

### 6.3 Load Testing

```bash
# Using k6
k6 run tests/performance/load_test.js

# Or using wrk
wrk -t12 -c400 -d30s http://localhost:8089/v1/chat/completions
```

---

## 7. Optimization Checklist

### Pre-Production

- [ ] Database indexes created
- [ ] Connection pooling configured
- [ ] Redis caching enabled
- [ ] LLM timeout configured
- [ ] Circuit breaker enabled
- [ ] Resource limits set
- [ ] HPA configured

### Post-Production

- [ ] Baseline metrics established
- [ ] Alerts configured
- [ ] Dashboards created
- [ ] Load tests passed
- [ ] Chaos engineering tests passed

### Ongoing

- [ ] Weekly performance reviews
- [ ] Monthly capacity planning
- [ ] Quarterly optimization
- [ ] Regular cache analysis

---

## 8. Troubleshooting Performance Issues

### High Latency

1. Check database query times
   ```bash
   kubectl exec -it postgres-0 -- psql -U jai_user -c "SELECT * FROM pg_stat_activity WHERE state = 'active';"
   ```

2. Check Redis cache hit rate
   ```bash
   redis-cli info stats | grep hit_rate
   ```

3. Check LLM provider latency
   ```bash
   curl http://localhost:8089/metrics | grep llm_latency
   ```

### High Memory Usage

1. Check for memory leaks
   ```bash
   kubectl top pods -n jai-production
   ```

2. Review Python garbage collection
   ```python
   import gc
   gc.collect()
   ```

### High CPU Usage

1. Profile application
   ```bash
   kubectl exec -it <pod> -- python -m cProfile -o profile.stats
   ```

2. Check for busy loops
   ```bash
   kubectl logs <pod> | grep -i timeout
   ```

---

## 9. Target Performance Summary

| Component | Metric | Target |
|-----------|--------|--------|
| API Gateway | P99 Latency | < 100ms |
| Cache | Hit Rate | > 30% |
| Database | Query Time | < 50ms |
| LLM (Local) | Response Time | < 2s |
| LLM (Cloud) | Response Time | < 5s |
| Overall | Error Rate | < 0.5% |
| Availability | Uptime | > 99.9% |

---

**Document Version**: 1.0  
**Last Updated**: 2026-03-22  
**Next Review**: 2026-06-22
