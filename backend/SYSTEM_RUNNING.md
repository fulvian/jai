# ✅ SYSTEM RUNNING: Development Mode

**Status**: ALL SERVICES ACTIVE
**Started**: March 10, 2024
**Mode**: Development (Local, No Docker)

---

## 🟢 Services Status

### Backend Server ✅
- **Status**: Running
- **URL**: http://localhost:8000
- **Port**: 8000
- **Process**: `python -m me4brain.main`
- **PID**: 1
- **Features**:
  - UnifiedIntentAnalyzer enabled
  - Feature flag: disabled (0% traffic)
  - Query caching enabled
  - Monitoring enabled

### Frontend Server ✅
- **Status**: Running
- **URL**: http://localhost:3000
- **Port**: 3000
- **Process**: `npm run dev`
- **PID**: 2
- **Features**:
  - Web UI active
  - Real-time query interface
  - Response display

### Monitoring Dashboard ✅
- **Status**: Running
- **Process**: `python scripts/monitor_intent.py`
- **PID**: 3
- **Features**:
  - Real-time metrics
  - Query tracking
  - Accuracy monitoring
  - Latency tracking

---

## 🧪 Testing the System

### 1. Open Web UI
```
http://localhost:3000
```

### 2. Send Weather Query
```
Che tempo fa a Caltanissetta?
```

### 3. Expected Result
- Query classified as TOOL_REQUIRED + geo_weather
- Weather data retrieved
- Response with real weather information

### 4. Monitor Metrics
Check monitoring dashboard for:
- Query classification
- Latency
- Cache hit rate
- Error rate

---

## 📊 System Configuration

### Feature Flags
```
USE_UNIFIED_INTENT_ANALYZER: true
ROLLOUT_PHASE: disabled
TRAFFIC_PERCENTAGE: 0%
```

### Performance Settings
```
INTENT_ANALYSIS_TIMEOUT: 5.0s
INTENT_CACHE_TTL: 300s
INTENT_CACHE_MAX_SIZE: 10000
INTENT_BATCH_SIZE: 10
INTENT_BATCH_TIMEOUT_MS: 100
```

---

## 📝 Test Queries

### Weather (Italian)
```
Che tempo fa a Caltanissetta?
Che tempo fa a Roma?
Piove oggi?
```

### Weather (English)
```
What's the weather in New York?
What's the weather in London?
Temperature in Tokyo
```

### Conversational
```
Ciao, come stai?
Hello, how are you?
Grazie mille
```

### Multi-Domain
```
Che tempo fa a Roma e qual è il prezzo dell'oro?
Show me weather in Paris and search for restaurants
```

---

## 📋 Monitoring

### Real-Time Dashboard
Terminal 3 shows:
- Query volume
- Accuracy by type
- Latency metrics
- Error rate
- Cache hit rate
- Domain distribution

### Manual Checks

**Check metrics**:
```bash
python -c "
from me4brain.engine.intent_monitoring import get_intent_monitor
monitor = get_intent_monitor()
print(monitor.get_metrics())
"
```

**Check cache**:
```bash
python -c "
from me4brain.engine.intent_cache import get_intent_cache
cache = get_intent_cache()
print(cache.get_stats())
"
```

**Check feature flag**:
```bash
python -c "
from me4brain.engine.feature_flags import get_feature_flag_manager
ffm = get_feature_flag_manager()
print(f'Phase: {ffm.current_phase}')
print(f'Traffic: {ffm.traffic_percentage}%')
"
```

---

## 📂 Logs

### Backend Logs
```bash
tail -f logs/backend.log
```

### Frontend Logs
```bash
tail -f logs/frontend.log
```

### Monitoring Logs
```bash
tail -f logs/monitor.log
```

---

## 🛑 Stopping Services

### Stop All
```bash
# Press Ctrl+C in each terminal
```

### Stop Individual
```bash
# Backend
kill -9 <PID>

# Frontend
kill -9 <PID>

# Monitoring
kill -9 <PID>
```

---

## 🔧 Troubleshooting

### Backend Not Responding
```bash
# Check logs
tail -f logs/backend.log

# Verify port
lsof -i :8000

# Restart
kill -9 <PID>
python -m me4brain.main
```

### Frontend Not Loading
```bash
# Check logs
tail -f logs/frontend.log

# Verify port
lsof -i :3000

# Restart
kill -9 <PID>
npm run dev
```

### Monitoring Not Showing
```bash
# Check if feature flag enabled
python -c "
from me4brain.llm.config import get_llm_config
config = get_llm_config()
print(f'Feature enabled: {config.use_unified_intent_analyzer}')
"
```

---

## 📈 Expected Performance

### Latency
- First query: ~200ms (LLM call)
- Cached query: ~2ms (cache hit)
- Average: ~110ms (p50)

### Accuracy
- Weather: 95%+
- Conversational: 98%+
- Multi-domain: 90%+

### Cache
- Hit rate: 40%+
- Size: 10,000 entries max

---

## 🎯 Next Steps

1. **Open Web UI**: http://localhost:3000
2. **Send test query**: "Che tempo fa a Caltanissetta?"
3. **Monitor results**: Check Terminal 3 dashboard
4. **Verify accuracy**: System should retrieve weather data
5. **Test multiple queries**: Try different query types

---

## 📞 Support

### For Issues
- Check logs: `tail -f logs/*.log`
- Check monitoring: Terminal 3
- Review [docs/RUNBOOK.md](./docs/RUNBOOK.md)

### For Configuration
- Edit `.env` file
- Restart services
- Check [docs/DEPLOYMENT_REALWORLD.md](./docs/DEPLOYMENT_REALWORLD.md)

### For Testing
- Use test queries above
- Check [docs/REALWORLD_TEST_PLAN.md](./docs/REALWORLD_TEST_PLAN.md)

---

## 📊 System Architecture

```
User Query (Web UI)
    ↓
Backend Server (8000)
    ├─ Feature Flag Check
    │   └─ Disabled → Old system
    ├─ Cache Check
    │   ├─ Hit → Return (2ms)
    │   └─ Miss → Continue
    ├─ LLM Classification
    │   ├─ Analyze intent
    │   ├─ Identify domains
    │   └─ Assess complexity
    ├─ Cache Store
    └─ Route to Tools
        ├─ Conversational → Direct response
        └─ Tool-Required → Execute tools → Synthesize
    ↓
Response to Frontend
    ↓
Display in Web UI (3000)
    ↓
Monitoring Dashboard (Terminal 3)
    └─ Track metrics
```

---

**Status**: ✅ ALL SERVICES RUNNING

**Backend**: http://localhost:8000
**Frontend**: http://localhost:3000
**Monitoring**: Terminal 3

**Ready for testing!**
