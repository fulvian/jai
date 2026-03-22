# Me4BrAIn Integrations

This document describes the external integrations supported by Me4BrAIn.

## 🔌 Model Context Protocol (MCP)

Me4BrAIn implements the **Model Context Protocol (MCP)** standard to allow external LLM applications (like LM Studio, Claude Desktop, or custom agents) to seamlessly interact with Me4BrAIn's internal capabilities.

### Supported Features

- **Tool Discovery**: Automatically exposes 50+ Me4BrAIn tools (Finance, NBA, Google Workspace, etc.).
- **Resources**: Exposes Semantic and Episodic memory as read-only resources.
- **Prompts**: Provides pre-defined system prompts for specific domain reasoning.
- **Transport**: Supports SSE (Server-Sent Events) for real-time streaming and tool execution.

### LM Studio Integration

To connect LM Studio to Me4BrAIn:

1.  **Start Me4BrAIn**: Run `bash scripts/start.sh`.
2.  **Configure LM Studio**: Add the following server to your `mcp.json` file:

```json
{
  "mcpServers": {
    "me4brain": {
      "url": "http://localhost:8089/mcp/sse"
    }
  }
}
```

3.  **Use Tools**: Open a chat in LM Studio, and you will see Me4BrAIn tools available in the plugins/tools menu.

### Technical Implementation

- **Library**: Built using `FastMCP`.
- **Mount Point**: Mounted at `/mcp` in the main FastAPI application.
- **SSE Endpoint**: Available at `/mcp/sse`.
- **Port**: Development port **8089**.

---

## 📅 Google Workspace (OAuth2)

Me4BrAIn integrates with Google APIs to manage:
- **Gmail**: Search and read emails.
- **Calendar**: List events and analyze meetings.
- **Drive/Docs**: Create and search documents.

*Documentation: [GOOGLE_WORKSPACE.md](./architecture/API_CATALOG.md)*

---

## 🏀 Sports (NBA API)

Deep integration with `nba_api` and specialized betting analytics.

*Documentation: [SPORTS_NBA_GUIDE.md](./architecture/blueprint_me4brain_v2.md)*

---

## 📈 Finance & Crypto

Integration with Yahoo Finance, Alpaca, Binance, and FMP (Financial Modeling Prep).

*Documentation: [FINANCE_GUIDE.md](./architecture/blueprint_me4brain_v2.md)*
