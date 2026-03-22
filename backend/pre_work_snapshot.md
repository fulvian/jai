# Pre-Work Snapshot - NBA Betting Analysis

## 1. OBJECTIVE
Execute a professional NBA betting analysis for tonight's games (2025-03-17/18) using 100% local LLMs and specialized domain tools.

## 2. ARCHITECTURE & STRUCTURE
- **Primary Reasoner**: `mlx-qwen3.5-9b-claude-4.6-opus-reasoning-distilled` (Local LM Studio)
- **Fast Synthesizer**: `qwen3.5-4b-mlx` (Local Ollama)
- **Domain Logic**: `src/me4brain/domains/sports_nba/`
- **Orchestration**: Director-led research workflow.

## 3. PROPOSED CHANGES (BATCH 1)
- Update `.env`:
  - `LLM_PRIMARY_MODEL`: `mlx-qwen3.5-9b-claude-4.6-opus-reasoning-distilled`
  - `LLM_PRIMARY_THINKING_MODEL`: `mlx-qwen3.5-9b-claude-4.6-opus-reasoning-distilled`
  - `LLM_AGENTIC_MODEL`: `mlx-qwen3.5-9b-claude-4.6-opus-reasoning-distilled`
  - `LLM_SYNTHESIS_MODEL`: `qwen3.5-4b-mlx`
  - `LLM_ROUTING_MODEL`: `mlx-qwen3.5-9b-claude-4.6-opus-reasoning-distilled`

## 4. ACCEPTANCE CRITERIA
- [ ] `.env` reflects the correct model strings.
- [ ] NBA domain tools are invoked successfully without WAF blocks.
- [ ] Final output contains a "Value Betting" proposal with at least 3 games.
- [ ] All reasoning is performed by local models (verified in logs).

## 5. RISK ASSESSMENT
- **Model Capability**: Local models might miss subtle betting nuances.
- **Data Freshness**: NBA tools must fetch real-time data for tonight's games.
- **WAF Blocks**: Potential for `curl_cffi` to be detected.
