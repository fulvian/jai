"""Monitor Evaluator.

Valuta monitor chiamando Me4BrAIn per dati e LLM per decisioni.
"""

from datetime import datetime
from typing import Any

import httpx
import structlog

from backend.proactive.monitors import (
    Decision,
    EvaluationResult,
    Monitor,
    MonitorState,
    MonitorType,
)

logger = structlog.get_logger(__name__)


class MonitorEvaluator:
    """Valutatore per monitor proattivi.

    Recupera dati da Me4BrAIn e usa LLM per decisioni.
    """

    def __init__(
        self,
        me4brain_url: str = "http://localhost:8000",
        nanogpt_api_key: str | None = None,
    ):
        """Inizializza evaluator.

        Args:
            me4brain_url: URL base Me4BrAIn
            nanogpt_api_key: API key per NanoGPT (opzionale)
        """
        self.me4brain_url = me4brain_url
        self.nanogpt_api_key = nanogpt_api_key
        self._http_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy init HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=60.0)
        return self._http_client

    async def close(self) -> None:
        """Chiude HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    # =========================================================================
    # Main Evaluation
    # =========================================================================

    async def evaluate(self, monitor: Monitor) -> EvaluationResult:
        """Valuta un monitor e ritorna il risultato.

        Il flusso dipende dal tipo di monitor:
        - PRICE_WATCH: Check prezzo vs threshold
        - SIGNAL_WATCH: Check indicatore tecnico
        - AUTONOMOUS: Full LLM analysis
        - SCHEDULED: Esegui task schedulato
        - EVENT_DRIVEN: Già triggerato da evento
        - HEARTBEAT: Reasoning periodico (OpenClaw-style)
        - TASK_REMINDER: Reminder generico
        - INBOX_WATCH: Monitoraggio email
        - CALENDAR_WATCH: Eventi imminenti
        - FILE_WATCH: Monitoraggio file system
        """
        logger.info(
            "evaluator_start",
            monitor_id=monitor.id,
            type=monitor.type.value,
        )

        try:
            # Finance monitors
            if monitor.type == MonitorType.PRICE_WATCH:
                return await self._evaluate_price_watch(monitor)
            elif monitor.type == MonitorType.SIGNAL_WATCH:
                return await self._evaluate_signal_watch(monitor)
            elif monitor.type == MonitorType.AUTONOMOUS:
                return await self._evaluate_autonomous(monitor)
            # System monitors
            elif monitor.type == MonitorType.SCHEDULED:
                return await self._evaluate_scheduled(monitor)
            elif monitor.type == MonitorType.EVENT_DRIVEN:
                return await self._evaluate_event_driven(monitor)
            # Generic monitors (OpenClaw-style)
            elif monitor.type == MonitorType.HEARTBEAT:
                return await self._evaluate_heartbeat(monitor)
            elif monitor.type == MonitorType.TASK_REMINDER:
                return await self._evaluate_task_reminder(monitor)
            elif monitor.type == MonitorType.INBOX_WATCH:
                return await self._evaluate_inbox_watch(monitor)
            elif monitor.type == MonitorType.CALENDAR_WATCH:
                return await self._evaluate_calendar_watch(monitor)
            elif monitor.type == MonitorType.FILE_WATCH:
                return await self._evaluate_file_watch(monitor)
            else:
                return EvaluationResult(
                    monitor_id=monitor.id,
                    error=f"Unknown monitor type: {monitor.type}",
                )

        except Exception as e:
            logger.error(
                "evaluator_error",
                monitor_id=monitor.id,
                error=str(e),
            )
            return EvaluationResult(
                monitor_id=monitor.id,
                error=str(e),
            )

    # =========================================================================
    # Type-Specific Evaluators
    # =========================================================================

    async def _evaluate_price_watch(self, monitor: Monitor) -> EvaluationResult:
        """Valuta PRICE_WATCH: prezzo vs soglia."""
        ticker = monitor.config.get("ticker", "")
        condition = monitor.config.get("condition", "below")
        threshold = float(monitor.config.get("threshold", 0))

        # Fetch current price da Me4BrAIn
        data = await self._fetch_stock_data(ticker)
        current_price = data.get("price", 0)

        # Check condition
        trigger = False
        if condition == "below" and current_price < threshold:
            trigger = True
        elif condition == "above" and current_price > threshold:
            trigger = True

        decision = Decision(
            recommendation="ALERT" if trigger else "WAIT",
            confidence=100 if trigger else 50,
            reasoning=f"Prezzo {ticker}: ${current_price:.2f} vs soglia ${threshold:.2f}",
            key_factors=[f"Condition: {condition}", f"Current: ${current_price:.2f}"],
        )

        return EvaluationResult(
            monitor_id=monitor.id,
            trigger=trigger,
            decision=decision,
            data_snapshot={"price": current_price, "threshold": threshold},
        )

    async def _evaluate_signal_watch(self, monitor: Monitor) -> EvaluationResult:
        """Valuta SIGNAL_WATCH: indicatore tecnico."""
        ticker = monitor.config.get("ticker", "")
        indicator = monitor.config.get("indicator", "rsi")
        condition = monitor.config.get("condition", "below")
        threshold = float(monitor.config.get("threshold", 30))

        # Fetch indicator da Me4BrAIn
        data = await self._fetch_technical_indicator(ticker, indicator)
        current_value = data.get("value", 50)

        # Check condition
        trigger = False
        if condition == "below" and current_value < threshold:
            trigger = True
        elif condition == "above" and current_value > threshold:
            trigger = True

        decision = Decision(
            recommendation="ALERT" if trigger else "WAIT",
            confidence=100 if trigger else 50,
            reasoning=f"{indicator.upper()} {ticker}: {current_value:.2f} vs soglia {threshold:.2f}",
            key_factors=[f"Indicator: {indicator}", f"Value: {current_value:.2f}"],
        )

        return EvaluationResult(
            monitor_id=monitor.id,
            trigger=trigger,
            decision=decision,
            data_snapshot={"indicator": indicator, "value": current_value},
        )

    async def _evaluate_autonomous(self, monitor: Monitor) -> EvaluationResult:
        """Valuta AUTONOMOUS: full LLM analysis con Tool Calling Engine.

        Usa AdvancedAutonomousEvaluator per:
        1. OBSERVE: Multi-tool data collection via Tool Calling Engine
        2. THINK: LLM analizza i dati
        3. DECIDE: BUY/SELL/HOLD con sizing e risk management
        4. ACT: Esegue azione (notify, trade, etc.)
        """
        from backend.proactive.autonomous_evaluator import (
            AdvancedAutonomousEvaluator,
            AgentConfig,
            AgentDecision,
            ActionType,
            RiskConfig,
        )

        # Build agent config from monitor
        risk_config = RiskConfig(
            max_position_pct=float(monitor.config.get("risk_cap", 0.02)),
            hitl_threshold_usd=float(monitor.config.get("hitl_threshold", 1000)),
            allowed_tickers=monitor.config.get("allowed_tickers", []),
        )

        action_str = monitor.config.get("action_type", "notify")
        action_type = (
            ActionType.TRADE if "trade" in action_str or "buy" in action_str else ActionType.NOTIFY
        )

        agent_config = AgentConfig(
            goal=monitor.config.get("goal", monitor.description),
            ticker=monitor.config.get("ticker"),
            tools=monitor.config.get("tools"),
            action_type=action_type,
            risk=risk_config,
            decision_prompt=monitor.config.get("decision_prompt"),
        )

        # Execute autonomous evaluation
        evaluator = AdvancedAutonomousEvaluator(
            me4brain_url=self.me4brain_url,
            nanogpt_api_key=self.nanogpt_api_key,
        )

        try:
            result = await evaluator.evaluate(agent_config)

            # Convert to EvaluationResult
            decision = Decision(
                recommendation=result.decision.action,
                confidence=result.decision.confidence,
                reasoning=result.decision.reasoning,
                key_factors=[result.decision.risk_assessment]
                if result.decision.risk_assessment
                else [],
                suggested_action=result.action_taken,
            )

            # Trigger if action taken or HITL pending
            trigger = result.decision.action in ["BUY", "SELL"] and result.decision.confidence >= 70

            return EvaluationResult(
                monitor_id=monitor.id,
                trigger=trigger or result.hitl_pending,
                decision=decision,
                data_snapshot=result.data_collected,
            )

        finally:
            await evaluator.close()

    async def _evaluate_scheduled(self, monitor: Monitor) -> EvaluationResult:
        """Valuta SCHEDULED: esegui task schedulato."""
        task = monitor.config.get("task", "")
        params = monitor.config.get("params", {})

        # Per task schedulati, sempre trigger (esegui il task)
        decision = Decision(
            recommendation="EXECUTE",
            confidence=100,
            reasoning=f"Scheduled task: {task}",
            key_factors=list(params.keys()),
            suggested_action=task,
        )

        return EvaluationResult(
            monitor_id=monitor.id,
            trigger=True,  # Scheduled tasks sempre triggerano
            decision=decision,
            data_snapshot={"task": task, "params": params},
        )

    async def _evaluate_event_driven(self, monitor: Monitor) -> EvaluationResult:
        """Valuta EVENT_DRIVEN: già triggerato da evento."""
        # Event-driven monitors sono triggerati esternamente
        # Qui facciamo solo logging
        decision = Decision(
            recommendation="EVENT_RECEIVED",
            confidence=100,
            reasoning="Event-driven monitor triggered externally",
            key_factors=[],
        )

        return EvaluationResult(
            monitor_id=monitor.id,
            trigger=True,
            decision=decision,
        )

    # =========================================================================
    # Generic Monitor Evaluators (OpenClaw-style)
    # =========================================================================

    async def _evaluate_heartbeat(self, monitor: Monitor) -> EvaluationResult:
        """Valuta HEARTBEAT: reasoning periodico autonomo."""
        goal = monitor.config.get("goal", "proactive_assistance")
        context_sources = monitor.config.get("context_sources", ["calendar", "memory"])
        min_urgency = monitor.config.get("min_urgency", "low")

        # Raccogli contesto
        context_data = {}

        if "calendar" in context_sources:
            context_data["calendar"] = await self._fetch_calendar_context()
        if "memory" in context_sources:
            context_data["memory"] = await self._fetch_memory_context()

        # LLM evaluation
        decision = await self._llm_heartbeat_evaluate(goal, context_data, min_urgency)

        # Trigger solo se LLM suggerisce azione
        trigger = decision.recommendation != "WAIT" and decision.confidence >= 60

        return EvaluationResult(
            monitor_id=monitor.id,
            trigger=trigger,
            decision=decision,
            data_snapshot=context_data,
        )

    async def _evaluate_task_reminder(self, monitor: Monitor) -> EvaluationResult:
        """Valuta TASK_REMINDER: reminder generico."""
        from datetime import datetime

        task_desc = monitor.config.get("task_description", "")
        due_date_str = monitor.config.get("due_date")
        priority = monitor.config.get("priority", "medium")

        # Check if due date is approaching
        trigger = False
        time_until = "N/A"

        if due_date_str:
            due_date = datetime.fromisoformat(due_date_str)
            now = datetime.utcnow()
            delta = due_date - now

            if delta.total_seconds() <= 0:
                trigger = True
                time_until = "OVERDUE"
            elif delta.total_seconds() <= 3600:  # 1 ora
                trigger = True
                time_until = f"{int(delta.total_seconds() / 60)} minuti"
            elif delta.total_seconds() <= 86400 and priority == "high":  # 24 ore
                trigger = True
                time_until = f"{int(delta.total_seconds() / 3600)} ore"

        decision = Decision(
            recommendation="REMIND" if trigger else "WAIT",
            confidence=100 if trigger else 30,
            reasoning=f"Task: {task_desc} - Scadenza: {time_until}",
            key_factors=[f"Priority: {priority}", f"Due: {due_date_str or 'N/A'}"],
            suggested_action=task_desc,
        )

        return EvaluationResult(
            monitor_id=monitor.id,
            trigger=trigger,
            decision=decision,
            data_snapshot={"task": task_desc, "time_until": time_until},
        )

    async def _evaluate_inbox_watch(self, monitor: Monitor) -> EvaluationResult:
        """Valuta INBOX_WATCH: monitoraggio email."""
        filters = monitor.config.get("filters", {})
        importance_threshold = monitor.config.get("importance_threshold", "medium")

        # Fetch inbox data via Me4BrAIn
        inbox_data = await self._fetch_inbox_context(filters)

        new_count = inbox_data.get("new_count", 0)
        important_count = inbox_data.get("important_count", 0)

        # Trigger based on importance
        trigger = False
        if importance_threshold == "low" and new_count > 0:
            trigger = True
        elif importance_threshold == "medium" and important_count > 0:
            trigger = True
        elif importance_threshold == "high" and important_count >= 3:
            trigger = True

        decision = Decision(
            recommendation="NOTIFY" if trigger else "WAIT",
            confidence=80 if trigger else 20,
            reasoning=f"Inbox: {new_count} nuove, {important_count} importanti",
            key_factors=[f"New: {new_count}", f"Important: {important_count}"],
        )

        return EvaluationResult(
            monitor_id=monitor.id,
            trigger=trigger,
            decision=decision,
            data_snapshot=inbox_data,
        )

    async def _evaluate_calendar_watch(self, monitor: Monitor) -> EvaluationResult:
        """Valuta CALENDAR_WATCH: eventi imminenti."""
        lookahead_minutes = monitor.config.get("lookahead_minutes", 30)
        event_types = monitor.config.get("event_types", ["meeting", "deadline"])

        # Fetch upcoming events
        events = await self._fetch_upcoming_events(lookahead_minutes)

        # Filter by type
        matching_events = [
            e for e in events if any(t in e.get("type", "").lower() for t in event_types)
        ]

        trigger = len(matching_events) > 0

        decision = Decision(
            recommendation="ALERT" if trigger else "WAIT",
            confidence=100 if trigger else 10,
            reasoning=f"{len(matching_events)} eventi nei prossimi {lookahead_minutes} min",
            key_factors=[e.get("title", "Unknown") for e in matching_events[:3]],
        )

        return EvaluationResult(
            monitor_id=monitor.id,
            trigger=trigger,
            decision=decision,
            data_snapshot={"events": matching_events},
        )

    async def _evaluate_file_watch(self, monitor: Monitor) -> EvaluationResult:
        """Valuta FILE_WATCH: monitoraggio file/directory."""
        import os
        from pathlib import Path

        path = monitor.config.get("path", "")
        events = monitor.config.get("events", ["modified"])

        # Check file existence and modification
        trigger = False
        file_info = {}

        try:
            p = Path(path)
            if p.exists():
                stat = p.stat()
                file_info = {
                    "exists": True,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                }

                # Check if modified since last check
                last_check = monitor.last_check
                if last_check and "modified" in events:
                    from datetime import datetime

                    if stat.st_mtime > last_check.timestamp():
                        trigger = True
            else:
                file_info = {"exists": False}
                if "deleted" in events:
                    trigger = True

        except Exception as e:
            file_info = {"error": str(e)}

        decision = Decision(
            recommendation="NOTIFY" if trigger else "WAIT",
            confidence=100 if trigger else 0,
            reasoning=f"File watch: {path}",
            key_factors=list(file_info.keys()),
        )

        return EvaluationResult(
            monitor_id=monitor.id,
            trigger=trigger,
            decision=decision,
            data_snapshot=file_info,
        )

    # =========================================================================
    # Context Fetching for Generic Monitors
    # =========================================================================

    async def _fetch_calendar_context(self) -> dict[str, Any]:
        """Fetch calendar context via Me4BrAIn."""
        client = await self._get_client()
        try:
            response = await client.post(
                f"{self.me4brain_url}/v1/cognitive/execute",
                json={
                    "query": "Lista i prossimi 5 eventi del mio calendario",
                    "domains": ["google_workspace"],
                },
            )
            if response.status_code == 200:
                return response.json().get("data", {})
        except Exception as e:
            logger.warning("fetch_calendar_context_error", error=str(e))

        return {"events": []}

    async def _fetch_memory_context(self) -> dict[str, Any]:
        """Fetch memory context via Me4BrAIn."""
        client = await self._get_client()
        try:
            response = await client.post(
                f"{self.me4brain_url}/v1/cognitive/execute",
                json={
                    "query": "Riassumi le ultime discussioni importanti",
                    "domains": ["memory"],
                },
            )
            if response.status_code == 200:
                return response.json().get("data", {})
        except Exception as e:
            logger.warning("fetch_memory_context_error", error=str(e))

        return {"summary": ""}

    async def _fetch_inbox_context(self, filters: dict[str, Any]) -> dict[str, Any]:
        """Fetch inbox context via Me4BrAIn."""
        client = await self._get_client()
        try:
            query = "Mostra le email non lette"
            if filters.get("from"):
                query += f" da {filters['from']}"

            response = await client.post(
                f"{self.me4brain_url}/v1/cognitive/execute",
                json={
                    "query": query,
                    "domains": ["google_workspace"],
                },
            )
            if response.status_code == 200:
                data = response.json().get("data", {})
                return {
                    "new_count": len(data.get("messages", [])),
                    "important_count": sum(
                        1 for m in data.get("messages", []) if m.get("important")
                    ),
                    "messages": data.get("messages", [])[:5],
                }
        except Exception as e:
            logger.warning("fetch_inbox_context_error", error=str(e))

        return {"new_count": 0, "important_count": 0, "messages": []}

    async def _fetch_upcoming_events(self, lookahead_minutes: int) -> list[dict[str, Any]]:
        """Fetch upcoming calendar events."""
        client = await self._get_client()
        try:
            response = await client.post(
                f"{self.me4brain_url}/v1/cognitive/execute",
                json={
                    "query": f"Mostra eventi nelle prossime {lookahead_minutes} minuti",
                    "domains": ["google_workspace"],
                },
            )
            if response.status_code == 200:
                return response.json().get("data", {}).get("events", [])
        except Exception as e:
            logger.warning("fetch_upcoming_events_error", error=str(e))

        return []

    async def _llm_heartbeat_evaluate(
        self,
        goal: str,
        context_data: dict[str, Any],
        min_urgency: str,
    ) -> Decision:
        """LLM evaluation per heartbeat."""
        prompt = f"""Sei un assistente personale proattivo. Il tuo obiettivo è: {goal}

## Contesto Attuale
{context_data}

## Regole
- Suggerisci azioni solo se veramente utili
- Urgenza minima richiesta: {min_urgency}
- Non disturbare inutilmente

Rispondi SOLO in JSON valido:
{{
  "recommendation": "NOTIFY" | "EXECUTE" | "WAIT",
  "confidence": 0-100,
  "reasoning": "spiegazione breve",
  "key_factors": ["factor1"],
  "suggested_action": "azione suggerita se applicabile"
}}"""

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
                },
            )

            if response.status_code == 200:
                import json

                content = response.json()["choices"][0]["message"]["content"]
                start = content.find("{")
                end = content.rfind("}") + 1
                if start >= 0 and end > start:
                    data = json.loads(content[start:end])
                    return Decision(**data)

        except Exception as e:
            logger.warning("llm_heartbeat_error", error=str(e))

        return Decision(
            recommendation="WAIT",
            confidence=10,
            reasoning="No significant action needed",
            key_factors=[],
        )

    # =========================================================================
    # Data Fetching from Me4BrAIn (Finance)
    # =========================================================================

    async def _fetch_stock_data(self, ticker: str) -> dict[str, Any]:
        """Fetch stock data via Me4BrAIn."""
        client = await self._get_client()
        try:
            response = await client.post(
                f"{self.me4brain_url}/v1/cognitive/execute",
                json={
                    "query": f"Get current stock data for {ticker}",
                    "domains": ["finance_crypto"],
                },
            )
            if response.status_code == 200:
                return response.json().get("data", {})
        except Exception as e:
            logger.warning("fetch_stock_data_error", ticker=ticker, error=str(e))

        return {"price": 0, "change": 0, "volume": 0}

    async def _fetch_technical_indicator(self, ticker: str, indicator: str) -> dict[str, Any]:
        """Fetch technical indicator via Me4BrAIn."""
        client = await self._get_client()
        try:
            response = await client.post(
                f"{self.me4brain_url}/v1/cognitive/execute",
                json={
                    "query": f"Get {indicator} for {ticker}",
                    "domains": ["finance_crypto"],
                },
            )
            if response.status_code == 200:
                data = response.json().get("data", {})
                # Extract indicator value from response
                return {"indicator": indicator, "value": data.get(indicator, 50)}
        except Exception as e:
            logger.warning(
                "fetch_indicator_error",
                ticker=ticker,
                indicator=indicator,
                error=str(e),
            )

        return {"indicator": indicator, "value": 50}

    async def _fetch_fundamentals(self, ticker: str) -> dict[str, Any]:
        """Fetch fundamental data via Me4BrAIn."""
        client = await self._get_client()
        try:
            response = await client.post(
                f"{self.me4brain_url}/v1/cognitive/execute",
                json={
                    "query": f"Get key financial metrics for {ticker}",
                    "domains": ["finance_crypto"],
                },
            )
            if response.status_code == 200:
                return response.json().get("data", {})
        except Exception as e:
            logger.warning("fetch_fundamentals_error", ticker=ticker, error=str(e))

        return {}

    async def _fetch_news(self, ticker: str) -> dict[str, Any]:
        """Fetch news via Me4BrAIn."""
        client = await self._get_client()
        try:
            response = await client.post(
                f"{self.me4brain_url}/v1/cognitive/execute",
                json={
                    "query": f"Latest news about {ticker}",
                    "domains": ["web_search"],
                },
            )
            if response.status_code == 200:
                return response.json().get("data", {})
        except Exception as e:
            logger.warning("fetch_news_error", ticker=ticker, error=str(e))

        return {"articles": []}

    # =========================================================================
    # LLM Evaluation
    # =========================================================================

    async def _llm_evaluate(
        self,
        ticker: str,
        goal: str,
        technicals: dict[str, Any],
        fundamentals: dict[str, Any],
        news: dict[str, Any],
    ) -> Decision:
        """Usa LLM per valutare opportunità."""
        prompt = f"""Sei un advisor finanziario. Analizza questi dati per {ticker}:

## Indicatori Tecnici
{technicals}

## Fondamentali
{fundamentals}

## News Recenti
{news}

L'utente vuole sapere se è il momento di {goal}.

Rispondi SOLO in JSON valido:
{{
  "recommendation": "BUY" | "SELL" | "HOLD" | "WAIT",
  "confidence": 0-100,
  "reasoning": "spiegazione breve",
  "key_factors": ["factor1", "factor2"],
  "suggested_action": "descrizione azione"
}}"""

        client = await self._get_client()

        try:
            # Prova NanoGPT
            response = await client.post(
                "https://nano-gpt.com/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.nanogpt_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "kimi-k2.5-free",
                    "messages": [{"role": "user", "content": prompt}],
                },
            )

            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                # Parse JSON from response
                import json

                # Find JSON in response
                start = content.find("{")
                end = content.rfind("}") + 1
                if start >= 0 and end > start:
                    data = json.loads(content[start:end])
                    return Decision(**data)

        except Exception as e:
            logger.warning("llm_evaluate_error", error=str(e))

        # Fallback decision
        return Decision(
            recommendation="WAIT",
            confidence=30,
            reasoning="Unable to complete analysis",
            key_factors=["LLM evaluation failed"],
        )
