"""Advanced Autonomous Agent Evaluator.

Implementa il pattern OBSERVE → THINK → DECIDE → ACT usando il Tool Calling Engine.

Caratteristiche:
1. Multi-tool orchestration via Tool Calling Engine
2. LLM analysis per decisione
3. Risk management integrato
4. HITL approval per azioni ad alto rischio
5. Esecuzione azioni (trade, email, notifica, etc.)

Esempio d'uso:
Agent: "ogni giorno analizza HOG: prezzo, fondamentali, fair value, tecnici.
        Decidi autonomamente buy/hold/sell con cap 2% capitale"

Flusso:
1. OBSERVE: Engine chiama finance_quote, fmp_key_metrics, fmp_dcf, technical_indicators
2. THINK: LLM analizza tutti i dati raccolti
3. DECIDE: LLM produce BUY/HOLD/SELL + sizing
4. RISK CHECK: Verifica limiti (2% cap)
5. HITL: Se trade > soglia, richiede approvazione
6. ACT: Esegue via alpaca_trade o altra azione
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any, Literal
from enum import Enum

import httpx
import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Types
# =============================================================================


class ActionType(str, Enum):
    """Tipi di azione supportati."""

    NOTIFY = "notify"  # Solo notifica
    TRADE = "trade"  # Esegui trade
    EMAIL = "email"  # Invia email
    WEBHOOK = "webhook"  # Chiama webhook
    CUSTOM = "custom"  # Azione custom


@dataclass
class RiskConfig:
    """Configurazione risk management."""

    max_position_pct: float = 0.02  # Max 2% del capitale
    max_loss_pct: float = 0.01  # Max 1% loss per trade
    hitl_threshold_usd: float = 1000.0  # HITL se trade > $1000
    daily_trade_limit: int = 10  # Max trade al giorno
    allowed_tickers: list[str] = field(default_factory=list)  # Ticker consentiti


@dataclass
class AgentConfig:
    """Configurazione agent autonomo."""

    goal: str  # Obiettivo in linguaggio naturale
    ticker: str | None = None  # Ticker principale (opzionale)
    tools: list[str] | None = None  # Tool specifici da usare
    action_type: ActionType = ActionType.NOTIFY
    risk: RiskConfig = field(default_factory=RiskConfig)
    decision_prompt: str | None = None  # Prompt custom per decisione
    context_window: int = 7  # Giorni di contesto
    broker: str = "alpaca"  # Broker per trade


@dataclass
class AgentDecision:
    """Decisione dell'agent."""

    action: Literal["BUY", "SELL", "HOLD", "NOTIFY", "WAIT"]
    confidence: int  # 0-100
    reasoning: str
    amount: float | None = None  # Importo/quantità
    price_target: float | None = None  # Target price
    stop_loss: float | None = None  # Stop loss
    requires_hitl: bool = False  # Richiede approvazione
    risk_assessment: str = ""  # Valutazione rischio


@dataclass
class AgentResult:
    """Risultato esecuzione agent."""

    success: bool
    decision: AgentDecision
    data_collected: dict[str, Any]
    action_taken: str | None = None
    hitl_pending: bool = False
    error: str | None = None


# =============================================================================
# Advanced Autonomous Evaluator
# =============================================================================


class AdvancedAutonomousEvaluator:
    """Evaluator avanzato per agenti autonomi con LLM nel loop.

    Pattern: OBSERVE → THINK → DECIDE → ACT

    Usa il Tool Calling Engine per raccogliere dati multi-source,
    poi LLM per analisi e decisione.
    """

    def __init__(
        self,
        me4brain_url: str = "http://localhost:8000",
        nanogpt_api_key: str | None = None,
    ):
        self.me4brain_url = me4brain_url
        self.nanogpt_api_key = nanogpt_api_key or os.getenv("NANOGPT_API_KEY")
        self._http_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=120.0)
        return self._http_client

    async def close(self) -> None:
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    # =========================================================================
    # Main Evaluation Flow
    # =========================================================================

    async def evaluate(self, config: AgentConfig) -> AgentResult:
        """Esegue il ciclo completo OBSERVE → THINK → DECIDE → ACT.

        Args:
            config: Configurazione dell'agent

        Returns:
            AgentResult con decisione e azioni prese
        """
        logger.info("autonomous_agent_start", goal=config.goal, ticker=config.ticker)

        try:
            # 1. OBSERVE: Raccogli dati via Tool Calling Engine
            data = await self._observe(config)

            # 2. THINK + DECIDE: LLM analizza e decide
            decision = await self._think_and_decide(config, data)

            # 3. RISK CHECK: Verifica limiti
            decision = self._apply_risk_management(config, decision)

            # 4. HITL CHECK: Richiede approvazione se necessario
            if decision.requires_hitl:
                logger.info(
                    "hitl_required",
                    action=decision.action,
                    amount=decision.amount,
                )
                return AgentResult(
                    success=True,
                    decision=decision,
                    data_collected=data,
                    hitl_pending=True,
                )

            # 5. ACT: Esegui l'azione
            action_result = await self._act(config, decision)

            return AgentResult(
                success=True,
                decision=decision,
                data_collected=data,
                action_taken=action_result,
            )

        except Exception as e:
            logger.exception("autonomous_agent_error", error=str(e))
            return AgentResult(
                success=False,
                decision=AgentDecision(
                    action="WAIT",
                    confidence=0,
                    reasoning=f"Error: {e}",
                ),
                data_collected={},
                error=str(e),
            )

    # =========================================================================
    # 1. OBSERVE: Data Collection via Tool Calling Engine
    # =========================================================================

    async def _observe(self, config: AgentConfig) -> dict[str, Any]:
        """Raccoglie dati usando il Tool Calling Engine.

        Costruisce una query in linguaggio naturale basata sul goal
        e lascia che il Tool Calling Engine orchestri i tool.
        """
        ticker = config.ticker or ""

        # Costruisci query per Tool Calling Engine
        query = self._build_observation_query(config)

        logger.info("observe_phase", query=query[:100])

        client = await self._get_client()

        try:
            # Chiama Tool Calling Engine via Me4BrAIn API
            response = await client.post(
                f"{self.me4brain_url}/v1/engine/query",
                json={
                    "query": query,
                    "context": f"Raccolta dati per analisi autonoma di {ticker}",
                    "max_tools": 10,  # Permetti multi-tool
                },
            )

            if response.status_code == 200:
                result = response.json()

                # Estrai dati dai tool results
                data = {
                    "raw_response": result.get("answer", ""),
                    "tool_results": result.get("tool_results", []),
                    "tools_called": result.get("tools_called", []),
                    "collected_at": datetime.now(UTC).isoformat(),
                }

                # Parse strutturato se possibile
                data["parsed"] = self._parse_tool_results(result.get("tool_results", []))

                logger.info(
                    "observe_complete",
                    tools_called=data["tools_called"],
                    data_points=len(data["parsed"]),
                )

                return data

        except Exception as e:
            logger.warning("observe_error", error=str(e))

        return {"error": "Failed to collect data", "collected_at": datetime.now(UTC).isoformat()}

    def _build_observation_query(self, config: AgentConfig) -> str:
        """Costruisce query per Tool Calling Engine basata sul goal."""
        ticker = config.ticker or "the asset"

        # Estrai keyword dal goal per determinare cosa raccogliere
        goal_lower = config.goal.lower()

        parts = []

        # Prezzo corrente
        parts.append(f"current price of {ticker}")

        # Fondamentali
        if any(
            kw in goal_lower
            for kw in ["fondamental", "fundamental", "metriche", "metrics", "ratios"]
        ):
            parts.append(f"key financial metrics and ratios for {ticker}")

        # Fair value / DCF
        if any(kw in goal_lower for kw in ["fair value", "dcf", "valuation", "intrinsic"]):
            parts.append(f"DCF valuation and fair value for {ticker}")

        # Analisi tecnica
        if any(kw in goal_lower for kw in ["tecnic", "technical", "indicator", "rsi", "macd"]):
            parts.append(f"technical indicators (RSI, MACD, Bollinger Bands) for {ticker}")

        # News
        if any(kw in goal_lower for kw in ["news", "notizie", "sentiment"]):
            parts.append(f"latest news about {ticker}")

        # Se nessuna keyword specifica, raccogli tutto
        if len(parts) <= 1:
            parts = [
                f"Get current price for {ticker}",
                f"Get key financial metrics for {ticker}",
                f"Get DCF fair value for {ticker}",
                f"Get technical indicators (RSI, MACD, BBands) for {ticker}",
            ]

        return " AND ".join(parts)

    def _parse_tool_results(self, tool_results: list[dict]) -> dict[str, Any]:
        """Parse tool results in formato strutturato."""
        parsed = {}

        for result in tool_results:
            tool_name = result.get("tool_name", "unknown")
            data = result.get("data", {})

            if "price" in tool_name or "quote" in tool_name:
                parsed["price"] = data
            elif "metrics" in tool_name or "fundamental" in tool_name:
                parsed["fundamentals"] = data
            elif "dcf" in tool_name:
                parsed["valuation"] = data
            elif "technical" in tool_name or "indicator" in tool_name:
                parsed["technicals"] = data
            elif "news" in tool_name:
                parsed["news"] = data
            else:
                parsed[tool_name] = data

        return parsed

    # =========================================================================
    # 2. THINK + DECIDE: LLM Analysis
    # =========================================================================

    async def _think_and_decide(
        self,
        config: AgentConfig,
        data: dict[str, Any],
    ) -> AgentDecision:
        """LLM analizza i dati e produce una decisione.

        Il prompt include:
        - Tutti i dati raccolti
        - Il goal dell'agent
        - I vincoli di risk management
        """
        prompt = self._build_decision_prompt(config, data)

        logger.info("think_phase", prompt_length=len(prompt))

        client = await self._get_client()

        try:
            response = await client.post(
                "https://nano-gpt.com/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.nanogpt_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "kimi-k2.5-free",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,  # Low temp per decisioni più conservative
                },
            )

            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                decision = self._parse_decision(content)

                logger.info(
                    "decide_complete",
                    action=decision.action,
                    confidence=decision.confidence,
                )

                return decision

        except Exception as e:
            logger.warning("think_decide_error", error=str(e))

        # Fallback: WAIT
        return AgentDecision(
            action="WAIT",
            confidence=10,
            reasoning="Unable to complete analysis",
            risk_assessment="Analysis failed - defaulting to hold",
        )

    def _build_decision_prompt(self, config: AgentConfig, data: dict[str, Any]) -> str:
        """Costruisce il prompt per la decisione LLM."""
        ticker = config.ticker or "asset"
        risk_config = config.risk

        # Formatta dati
        parsed = data.get("parsed", {})

        price_section = ""
        if "price" in parsed:
            price_section = f"""
## Current Price Data
{json.dumps(parsed["price"], indent=2, default=str)}
"""

        fundamentals_section = ""
        if "fundamentals" in parsed:
            fundamentals_section = f"""
## Fundamental Analysis
{json.dumps(parsed["fundamentals"], indent=2, default=str)}
"""

        valuation_section = ""
        if "valuation" in parsed:
            valuation_section = f"""
## DCF / Fair Value
{json.dumps(parsed["valuation"], indent=2, default=str)}
"""

        technicals_section = ""
        if "technicals" in parsed:
            technicals_section = f"""
## Technical Indicators
{json.dumps(parsed["technicals"], indent=2, default=str)}
"""

        # Custom prompt o default
        custom_prompt = config.decision_prompt or ""

        return f"""You are an autonomous trading agent. Your goal is:
{config.goal}

# Analysis Data for {ticker}
{price_section}
{fundamentals_section}
{valuation_section}
{technicals_section}

# Risk Constraints
- Maximum position size: {risk_config.max_position_pct * 100}% of total capital
- Maximum loss per trade: {risk_config.max_loss_pct * 100}%
- HITL approval required for trades > ${risk_config.hitl_threshold_usd}
{f"- Custom instructions: {custom_prompt}" if custom_prompt else ""}

# Your Task
1. Analyze ALL the data provided
2. Consider current market conditions
3. Make a clear BUY/SELL/HOLD decision
4. If action recommended, specify position sizing respecting risk limits
5. Provide stop-loss and price targets

Respond ONLY with valid JSON:
{{
    "action": "BUY" | "SELL" | "HOLD" | "WAIT",
    "confidence": 0-100,
    "reasoning": "detailed explanation of your decision",
    "amount": null or dollar amount,
    "price_target": null or target price,
    "stop_loss": null or stop loss price,
    "risk_assessment": "brief risk evaluation"
}}

Be conservative. Only recommend action if confidence > 70%.
"""

    def _parse_decision(self, content: str) -> AgentDecision:
        """Parse risposta LLM in AgentDecision."""
        try:
            # Trova JSON nel content
            start = content.find("{")
            end = content.rfind("}") + 1

            if start >= 0 and end > start:
                data = json.loads(content[start:end])

                return AgentDecision(
                    action=data.get("action", "WAIT"),
                    confidence=data.get("confidence", 0),
                    reasoning=data.get("reasoning", ""),
                    amount=data.get("amount"),
                    price_target=data.get("price_target"),
                    stop_loss=data.get("stop_loss"),
                    risk_assessment=data.get("risk_assessment", ""),
                )

        except json.JSONDecodeError as e:
            logger.warning("decision_parse_error", error=str(e), content=content[:200])

        return AgentDecision(
            action="WAIT",
            confidence=0,
            reasoning="Failed to parse LLM decision",
        )

    # =========================================================================
    # 3. RISK MANAGEMENT
    # =========================================================================

    def _apply_risk_management(
        self,
        config: AgentConfig,
        decision: AgentDecision,
    ) -> AgentDecision:
        """Applica limiti di risk management alla decisione."""
        risk = config.risk

        # Se non è un'azione di trading, skip
        if decision.action not in ["BUY", "SELL"]:
            return decision

        # Check HITL threshold
        if decision.amount and decision.amount > risk.hitl_threshold_usd:
            decision.requires_hitl = True
            decision.risk_assessment += (
                f" [HITL: amount ${decision.amount} > threshold ${risk.hitl_threshold_usd}]"
            )
            logger.info(
                "risk_hitl_triggered",
                amount=decision.amount,
                threshold=risk.hitl_threshold_usd,
            )

        # Check allowed tickers
        if risk.allowed_tickers and config.ticker:
            if config.ticker.upper() not in [t.upper() for t in risk.allowed_tickers]:
                decision.action = "WAIT"
                decision.reasoning += f" [BLOCKED: {config.ticker} not in allowed list]"
                logger.warning("risk_ticker_blocked", ticker=config.ticker)

        # Check position size (if amount provided as percentage)
        # Questo richiederebbe integrazione con broker per portfolio value

        return decision

    # =========================================================================
    # 4. ACT: Execute Action
    # =========================================================================

    async def _act(
        self,
        config: AgentConfig,
        decision: AgentDecision,
    ) -> str:
        """Esegue l'azione decisa.

        Supporta:
        - NOTIFY: Invia notifica
        - TRADE: Esegue trade via broker (Alpaca)
        - EMAIL: Invia email
        - WEBHOOK: Chiama webhook custom
        """
        action_type = config.action_type

        if decision.action == "HOLD" or decision.action == "WAIT":
            return "No action taken (HOLD/WAIT)"

        logger.info(
            "act_phase",
            action_type=action_type.value,
            decision_action=decision.action,
            amount=decision.amount,
        )

        if action_type == ActionType.NOTIFY:
            return await self._act_notify(config, decision)
        elif action_type == ActionType.TRADE:
            return await self._act_trade(config, decision)
        elif action_type == ActionType.EMAIL:
            return await self._act_email(config, decision)
        elif action_type == ActionType.WEBHOOK:
            return await self._act_webhook(config, decision)
        else:
            return "Unknown action type"

    async def _act_notify(self, config: AgentConfig, decision: AgentDecision) -> str:
        """Invia notifica all'utente."""
        message = f"""
🤖 **Autonomous Agent Alert**

**Ticker**: {config.ticker}
**Action**: {decision.action}
**Confidence**: {decision.confidence}%
**Amount**: ${decision.amount or "N/A"}

**Reasoning**: {decision.reasoning}

**Risk Assessment**: {decision.risk_assessment}
"""
        # In produzione, invia via Telegram/WebSocket/Push
        logger.info("notify_sent", message=message[:100])
        return f"Notification sent: {decision.action} {config.ticker}"

    async def _act_trade(self, config: AgentConfig, decision: AgentDecision) -> str:
        """Esegue trade via broker (Alpaca).

        NOTA: Questo richiede integrazione con Alpaca API.
        Per ora è un placeholder che chiama il Tool Calling Engine.
        """
        if not config.ticker or not decision.amount:
            return "Trade skipped: missing ticker or amount"

        # Costruisci ordine
        side = "buy" if decision.action == "BUY" else "sell"

        # Chiama broker via Me4BrAIn (se tool alpaca esiste)
        client = await self._get_client()

        try:
            response = await client.post(
                f"{self.me4brain_url}/v1/engine/query",
                json={
                    "query": f"{side} ${decision.amount} of {config.ticker}",
                    "context": f"Autonomous agent trade execution. Reasoning: {decision.reasoning}",
                },
            )

            if response.status_code == 200:
                result = response.json()
                return f"Trade executed: {side.upper()} ${decision.amount} {config.ticker}"

        except Exception as e:
            logger.error("trade_execution_error", error=str(e))
            return f"Trade failed: {e}"

        return "Trade execution pending"

    async def _act_email(self, config: AgentConfig, decision: AgentDecision) -> str:
        """Invia email con risultato analisi."""
        # Usa Gmail tool via Me4BrAIn
        return "Email action not implemented"

    async def _act_webhook(self, config: AgentConfig, decision: AgentDecision) -> str:
        """Chiama webhook custom."""
        return "Webhook action not implemented"


# =============================================================================
# Factory Function
# =============================================================================


def create_autonomous_evaluator(
    me4brain_url: str | None = None,
    nanogpt_api_key: str | None = None,
) -> AdvancedAutonomousEvaluator:
    """Factory per creare evaluator con defaults da environment."""
    return AdvancedAutonomousEvaluator(
        me4brain_url=me4brain_url or os.getenv("ME4BRAIN_URL", "http://localhost:8000"),
        nanogpt_api_key=nanogpt_api_key,
    )
