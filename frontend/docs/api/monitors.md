# Monitor API Documentation

**Version**: 1.0.0  
**Base URL**: `http://localhost:3030/api`  
**Authentication**: `x-user-id` header required

---

## Overview

The Monitor API provides endpoints for managing proactive monitors with real-time notifications, intelligent scheduling, and parallel evaluation.

---

## Authentication

All endpoints require the `x-user-id` header:

```http
x-user-id: {userId}
```

---

## Endpoints

### Create Monitor

Create a new monitor with specified configuration.

**Endpoint**: `POST /monitors`

**Headers**:
```http
Content-Type: application/json
x-user-id: {userId}
```

**Request Body**:
```json
{
  "type": "PRICE_WATCH" | "SIGNAL_WATCH" | "AUTONOMOUS" | "SCHEDULED" | "EVENT_DRIVEN" | "HEARTBEAT" | "TASK_REMINDER" | "INBOX_WATCH" | "CALENDAR_WATCH" | "FILE_WATCH",
  "name": "string",
  "description": "string (optional)",
  "config": {
    // Type-specific configuration
  },
  "interval_minutes": "number",
  "notify_channels": ["push"]
}
```

**Response**: `201 Created`
```json
{
  "success": true,
  "monitor": {
    "id": "uuid",
    "user_id": "string",
    "type": "PRICE_WATCH",
    "name": "string",
    "description": "string",
    "config": {},
    "state": "ACTIVE",
    "interval_minutes": 5,
    "notify_channels": ["push"],
    "created_at": "ISO8601",
    "updated_at": "ISO8601",
    "checks_count": 0,
    "triggers_count": 0,
    "history": []
  },
  "message": "Monitor created successfully"
}
```

**Example**:
```bash
curl -X POST http://localhost:3030/api/monitors \
  -H "Content-Type: application/json" \
  -H "x-user-id: user123" \
  -d '{
    "type": "PRICE_WATCH",
    "name": "AAPL Alert",
    "description": "Alert when AAPL drops below $150",
    "config": {
      "ticker": "AAPL",
      "condition": "below",
      "threshold": 150
    },
    "interval_minutes": 5,
    "notify_channels": ["push"]
  }'
```

---

### List Monitors

Get all monitors for the authenticated user.

**Endpoint**: `GET /monitors`

**Headers**:
```http
x-user-id: {userId}
```

**Response**: `200 OK`
```json
{
  "success": true,
  "monitors": [
    {
      "id": "uuid",
      "user_id": "string",
      "type": "PRICE_WATCH",
      "name": "string",
      "state": "ACTIVE",
      "created_at": "ISO8601",
      "last_check": "ISO8601",
      "next_check": "ISO8601",
      "checks_count": 10,
      "triggers_count": 2
    }
  ],
  "total": 1
}
```

**Example**:
```bash
curl http://localhost:3030/api/monitors \
  -H "x-user-id: user123"
```

---

### Get Monitor

Get details of a specific monitor.

**Endpoint**: `GET /monitors/:id`

**Headers**:
```http
x-user-id: {userId}
```

**Response**: `200 OK`
```json
{
  "success": true,
  "monitor": {
    "id": "uuid",
    "user_id": "string",
    "type": "PRICE_WATCH",
    "name": "string",
    "description": "string",
    "config": {},
    "state": "ACTIVE",
    "interval_minutes": 5,
    "notify_channels": ["push"],
    "created_at": "ISO8601",
    "updated_at": "ISO8601",
    "last_check": "ISO8601",
    "next_check": "ISO8601",
    "checks_count": 10,
    "triggers_count": 2,
    "history": []
  }
}
```

**Error**: `404 Not Found`
```json
{
  "success": false,
  "error": "Monitor not found"
}
```

**Example**:
```bash
curl http://localhost:3030/api/monitors/abc-123 \
  -H "x-user-id: user123"
```

---

### Pause Monitor

Pause a running monitor.

**Endpoint**: `POST /monitors/:id/pause`

**Headers**:
```http
x-user-id: {userId}
```

**Response**: `200 OK`
```json
{
  "success": true,
  "monitor": {
    "id": "uuid",
    "state": "PAUSED",
    "updated_at": "ISO8601"
  }
}
```

**Example**:
```bash
curl -X POST http://localhost:3030/api/monitors/abc-123/pause \
  -H "x-user-id: user123"
```

---

### Resume Monitor

Resume a paused monitor.

**Endpoint**: `POST /monitors/:id/resume`

**Headers**:
```http
x-user-id: {userId}
```

**Response**: `200 OK`
```json
{
  "success": true,
  "monitor": {
    "id": "uuid",
    "state": "ACTIVE",
    "updated_at": "ISO8601",
    "next_check": "ISO8601"
  }
}
```

**Example**:
```bash
curl -X POST http://localhost:3030/api/monitors/abc-123/resume \
  -H "x-user-id: user123"
```

---

### Trigger Monitor

Force immediate evaluation of a monitor.

**Endpoint**: `POST /monitors/:id/trigger`

**Headers**:
```http
x-user-id: {userId}
```

**Response**: `200 OK`
```json
{
  "success": true,
  "message": "Monitor evaluation triggered"
}
```

**Example**:
```bash
curl -X POST http://localhost:3030/api/monitors/abc-123/trigger \
  -H "x-user-id: user123"
```

---

### Delete Monitor

Delete a monitor permanently.

**Endpoint**: `DELETE /monitors/:id`

**Headers**:
```http
x-user-id: {userId}
```

**Response**: `204 No Content`

**Example**:
```bash
curl -X DELETE http://localhost:3030/api/monitors/abc-123 \
  -H "x-user-id: user123"
```

---

## Monitor Types & Configurations

### PRICE_WATCH

Monitor stock/crypto prices with threshold alerts.

**Config**:
```json
{
  "ticker": "AAPL",
  "condition": "above" | "below",
  "threshold": 150
}
```

---

### SIGNAL_WATCH

Monitor technical indicators (RSI, MACD).

**Config**:
```json
{
  "ticker": "TSLA",
  "indicator": "RSI" | "MACD",
  "condition": "above" | "below",
  "threshold": 30
}
```

---

### AUTONOMOUS

AI-powered autonomous trading decisions.

**Config**:
```json
{
  "ticker": "BTC",
  "goal": "maximize_returns",
  "min_confidence": 80
}
```

---

### SCHEDULED

Cron-based scheduled tasks.

**Config**:
```json
{
  "cron_expression": "0 9 * * *",
  "task": "daily_report"
}
```

---

### HEARTBEAT

Periodic health checks.

**Config**:
```json
{
  "goal": "check_services",
  "min_urgency": 5
}
```

---

### TASK_REMINDER

Task deadline reminders.

**Config**:
```json
{
  "task": "Complete project proposal",
  "due_date": "2026-03-01T12:00:00Z"
}
```

---

## WebSocket Integration

### Connection

```javascript
const ws = new WebSocket('ws://localhost:3030/ws');
```

### Message Types

#### Monitor Alert

Sent when a monitor triggers.

```json
{
  "type": "monitor:alert",
  "data": {
    "monitorId": "uuid",
    "monitorName": "AAPL Alert",
    "type": "PRICE_WATCH",
    "title": "Price Alert",
    "message": "AAPL dropped below $150",
    "recommendation": "SELL",
    "confidence": 95,
    "ticker": "AAPL",
    "triggeredAt": 1234567890
  },
  "timestamp": 1234567890
}
```

#### Monitor Update

Sent when monitor state changes.

```json
{
  "type": "monitor:update",
  "data": {
    "monitorId": "uuid",
    "state": "ACTIVE" | "PAUSED" | "TRIGGERED" | "COMPLETED" | "ERROR",
    "lastCheck": "ISO8601",
    "nextCheck": "ISO8601"
  },
  "timestamp": 1234567890
}
```

### Example

```javascript
const ws = new WebSocket('ws://localhost:3030/ws');

ws.onopen = () => {
  console.log('Connected to monitor notifications');
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  
  if (msg.type === 'monitor:alert') {
    console.log('Alert:', msg.data.title, msg.data.message);
    // Show notification to user
  }
  
  if (msg.type === 'monitor:update') {
    console.log('Monitor updated:', msg.data.monitorId, msg.data.state);
    // Update UI
  }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('Disconnected from monitor notifications');
  // Implement reconnection logic
};
```

---

## Error Codes

| Code | Description                                            |
| ---- | ------------------------------------------------------ |
| 400  | Bad Request - Invalid request body or parameters       |
| 401  | Unauthorized - Missing or invalid x-user-id header     |
| 404  | Not Found - Monitor not found                          |
| 500  | Internal Server Error - Server error during processing |

---

## Rate Limiting

- **Create Monitor**: 10 requests per minute per user
- **List Monitors**: 60 requests per minute per user
- **Other Endpoints**: 30 requests per minute per user

---

## Best Practices

1. **Use appropriate intervals**: Don't set interval_minutes < 5 for production monitors
2. **Handle WebSocket reconnection**: Implement exponential backoff for reconnection
3. **Validate configurations**: Use Zod schemas to validate monitor configs before sending
4. **Monitor cleanup**: Delete unused monitors to reduce system load
5. **Error handling**: Always handle 404 and 500 errors gracefully

---

## Examples

### Complete Flow

```typescript
// 1. Create monitor
const response = await fetch('http://localhost:3030/api/monitors', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'x-user-id': 'user123'
  },
  body: JSON.stringify({
    type: 'PRICE_WATCH',
    name: 'Tesla Alert',
    config: {
      ticker: 'TSLA',
      condition: 'above',
      threshold: 200
    },
    interval_minutes: 15,
    notify_channels: ['push']
  })
});

const { monitor } = await response.json();
console.log('Monitor created:', monitor.id);

// 2. Connect WebSocket
const ws = new WebSocket('ws://localhost:3030/ws');
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === 'monitor:alert') {
    alert(`${msg.data.title}: ${msg.data.message}`);
  }
};

// 3. Pause monitor
await fetch(`http://localhost:3030/api/monitors/${monitor.id}/pause`, {
  method: 'POST',
  headers: { 'x-user-id': 'user123' }
});

// 4. Resume monitor
await fetch(`http://localhost:3030/api/monitors/${monitor.id}/resume`, {
  method: 'POST',
  headers: { 'x-user-id': 'user123' }
});

// 5. Trigger manual evaluation
await fetch(`http://localhost:3030/api/monitors/${monitor.id}/trigger`, {
  method: 'POST',
  headers: { 'x-user-id': 'user123' }
});

// 6. Delete monitor
await fetch(`http://localhost:3030/api/monitors/${monitor.id}`, {
  method: 'DELETE',
  headers: { 'x-user-id': 'user123' }
});
```

---

## Support

For issues or questions:
- GitHub Issues: https://github.com/fulvian/PersAn/issues
- Documentation: https://github.com/fulvian/PersAn/tree/master/docs
