"""Response Synthesizer - Combine tool results into natural language.

The synthesizer is responsible for:
1. Formatting tool results for the LLM
2. Generating a coherent natural language response
3. Handling partial failures gracefully
"""

from __future__ import annotations

import asyncio

from typing import Any

import structlog

from me4brain.engine.types import ToolResult, StreamChunk
from me4brain.llm.models import LLMRequest, Message
from me4brain.llm.provider_factory import resolve_model_client

logger = structlog.get_logger(__name__)

# Se il context dei risultati supera questa soglia (chars), attiva il map-reduce (Tier 2)
MAP_THRESHOLD_CHARS = 16_000


class ResponseSynthesizer:
    """Synthesizes tool results into a natural language response.

    The LLM receives:
    - Original user query
    - Results from all executed tools

    And generates a coherent response that integrates all data.

    Example:
        synthesizer = ResponseSynthesizer(llm_client)
        answer = await synthesizer.synthesize(
            query="Prezzo Bitcoin e meteo Roma",
            results=[
                ToolResult(tool_name="coingecko_price", success=True, data={"bitcoin": ...}),
                ToolResult(tool_name="openmeteo_weather", success=True, data={"temp": 15}),
            ]
        )
    """

    def __init__(
        self,
        llm_client: Any,  # NanoGPTClient
        model: str = "deepseek-chat",
        is_local: bool = False,
        overflow_strategy: str | None = None,
    ) -> None:
        """Initialize synthesizer.

        Args:
            llm_client: LLM client for generation
            model: Model to use for synthesis
            is_local: Whether the model is a local one (e.g. Qwen 3.5 via MLX)
            overflow_strategy: Override strategy for context overflow handling
        """
        self._llm = llm_client
        self._model = model
        self._is_local = is_local
        self._overflow_strategy = overflow_strategy

    def _get_overflow_strategy(self) -> str:
        """Read overflow strategy from current config."""
        if self._overflow_strategy:
            return self._overflow_strategy
        try:
            from me4brain.llm.config import get_llm_config

            config = get_llm_config()
            return config.context_overflow_strategy
        except Exception:
            return "map_reduce"

    def _truncate_context(self, context: str, max_chars: int = 12_000) -> str:
        """Truncate context keeping the most recent parts."""
        if len(context) <= max_chars:
            return context
        return "...[contesto precedente troncato]...\n\n" + context[-max_chars:]

    async def _cloud_fallback_synthesis(self, results: list[ToolResult], query: str) -> str:
        """Use cloud model for synthesis when context overflows."""
        try:
            from me4brain.llm.provider_factory import get_reasoning_client

            cloud_client = await get_reasoning_client()
            results_context = self._format_results(results)

            prompt = f"""Query: {query}

Dati (contesto esteso):
{results_context}

Genera una risposta completa in italiano."""

            resolved_client, actual_model = resolve_model_client("mistral-large-latest")
            request = LLMRequest(
                model=actual_model,
                messages=[
                    Message(role="system", content=self._get_full_system_prompt()),
                    Message(role="user", content=prompt),
                ],
                temperature=0.3,
                max_tokens=8192,
            )

            response = await resolved_client.generate_response(request)
            return response.content or results_context[:5000]
        except Exception as e:
            logger.warning("cloud_fallback_failed", error=str(e))
            return self._truncate_context(self._format_results(results))

    async def synthesize(
        self,
        query: str,
        results: list[ToolResult],
        context: str | None = None,
    ) -> str:
        """Synthesize tool results into a natural language response.

        Args:
            query: Original user query
            results: List of ToolResult objects
            context: Optional additional context

        Returns:
            Natural language response integrating all tool data
        """
        if not results:
            return "Non sono riuscito a recuperare dati per questa richiesta."

        # Check if all tools failed
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        if not successful:
            # All tools failed - provide informative error
            return self._generate_partial_response(results, query, failed)

        # Build context from results
        results_context = self._format_results(results)

        # Apply configured overflow strategy when context exceeds threshold
        if len(results_context) > MAP_THRESHOLD_CHARS:
            strategy = self._get_overflow_strategy()
            logger.info(
                "synthesizer_overflow_triggered",
                context_size=len(results_context),
                strategy=strategy,
            )

            if strategy == "map_reduce":
                results_context = await self._map_reduce_results(results, query)
            elif strategy == "truncate":
                results_context = self._truncate_context(results_context)
            elif strategy == "cloud_fallback":
                results_context = await self._cloud_fallback_synthesis(results, query)

        # Build prompt
        prompt = self._build_prompt(query, results_context, context, failed)

        # Create LLM request
        resolved_client, actual_model = resolve_model_client(self._model)
        request = LLMRequest(
            model=actual_model,
            messages=[
                Message(role="system", content=self._get_system_prompt()),
                Message(role="user", content=prompt),
            ],
            temperature=0.3,  # Slightly creative for natural language
            max_tokens=16384,  # Increased for complex multi-source reports
        )

        try:
            # Wrap synthesis LLM call with timeout protection (900 seconds - generous development)
            # Synthesis can be expensive with large contexts
            try:
                response = await asyncio.wait_for(
                    resolved_client.generate_response(request),
                    timeout=900.0,  # 900 second timeout (development)
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "synthesizer_timeout",
                    timeout_seconds=900,
                    query_preview=query[:50],
                    fallback="partial_response",
                )
                return self._fallback_response(results)

            # Gestisci sia reasoning nativo che <think> tags
            native_reasoning = response.reasoning if response else None

            if response.choices and response.choices[0].message.content:
                raw_content = response.choices[0].message.content

                # Estrai thinking usando la stessa logica della versione streaming
                answer = self._extract_thinking_from_content(raw_content)

                if native_reasoning:
                    logger.info(
                        "synthesizer_complete",
                        query_preview=query[:50],
                        tools_used=len(successful),
                        tools_failed=len(failed),
                        answer_length=len(answer),
                        has_native_reasoning=True,
                        reasoning_length=len(native_reasoning),
                    )
                else:
                    logger.info(
                        "synthesizer_complete",
                        query_preview=query[:50],
                        tools_used=len(successful),
                        tools_failed=len(failed),
                        answer_length=len(answer),
                    )

                return answer

            logger.warning("synthesizer_empty_response", query=query[:80])
            return self._fallback_response(results)

        except Exception as e:
            logger.error(
                "synthesizer_failed",
                error=str(e),
                error_type=type(e).__name__,
                query_preview=query[:80],
                model=self._model,
                prompt_size=len(prompt) if "prompt" in locals() else -1,
                tools_count=len(results),
                tools_ok=len(successful),
            )
            return self._fallback_response(results)

    def _generate_partial_response(
        self,
        results: list[ToolResult],
        query: str,
        failed: list[ToolResult],
    ) -> str:
        """Generate informative response when some or all tools fail.

        Provides feedback on what was attempted and what failed,
        instead of a generic error message.
        """
        successful = [r for r in results if r.success]

        if not successful and not failed:
            return "Non sono riuscito a recuperare dati per questa richiesta."

        # Analyze what was attempted
        failed_tools = {r.tool_name for r in failed}
        successful_tools = {r.tool_name for r in successful}

        # Build informative message
        parts = []

        if successful:
            parts.append(f"Ho trovato risultati da: {', '.join(sorted(successful_tools))}")

        if failed_tools:
            parts.append(
                f"Ma non sono riuscito a trovare informazioni da: {', '.join(sorted(failed_tools))}"
            )

        # Add specific hints based on failed tools
        if "semanticscholar_search" in failed_tools or "arxiv_search" in failed_tools:
            parts.append("(Nessun paper trovato con i criteri specificati)")

        if "web_search" in failed_tools or "duckduckgo_search" in failed_tools:
            parts.append("(Nessun risultato web trovato)")

        message = ". ".join(parts)
        if not message:
            message = "Non sono riuscito a recuperare i dati richiesti."

        logger.info(
            "synthesizer_partial_response",
            query_preview=query[:50],
            successful_tools=len(successful),
            failed_tools=len(failed),
            message=message,
        )

        return message

    def _extract_thinking_from_content(self, content: str) -> str:
        """Extract and remove <think>...</think> thinking tags from content.

        This is used by both streaming and non-streaming synthesis methods
        to ensure thinking doesn't appear in the final response.

        Args:
            content: Raw content from LLM that may contain thinking tags

        Returns:
            Content with thinking tags removed
        """
        if not content:
            return content

        # Check for both opening and closing thinking tags
        if "<think>" not in content or "</think>" not in content:
            # Missing at least one tag - return as is
            return content

        # Simple approach: remove all <think>...</think> pairs
        # We need to handle them sequentially because they can be nested
        result = content
        while "<think>" in result and "</think>" in result:
            start = result.find("<think>")
            end = result.find("</think>", start)
            if end == -1:
                # No closing tag found
                break
            # Remove from start to end+len("</think>")
            result = result[:start] + result[end + len("</think>") :]

        return result.strip()

    def _get_system_prompt(self) -> str:
        """Get system prompt for synthesis. Selects between full and lite version."""
        if self._is_local:
            return self._get_lite_system_prompt()
        return self._get_full_system_prompt()

    def _get_lite_system_prompt(self) -> str:
        """Simplified prompt for local models with smaller parameter counts."""
        return """Sei un assistente AI. Il tuo compito è generare una risposta naturale basata sui dati forniti.

REGOLE ESSENZIALI:
1. Rispondi in ITALIANO in modo coerente e discorsivo.
2. Usa SOLO i dati presenti nei risultati dei tool. Non inventare nulla.
3. Se un'operazione è fallita, informa l'utente con onestà.
4. Formatta la risposta usando Markdown (titoli ##, grassetti, elenchi).
5. Includi sempre i link (webViewLink) se disponibili per i documenti.
6. Per calcoli finanziari, presenta i dati in una tabella se possibile.
7. Sii sintetico ma completo. Evita ripetizioni inutili."""

    def _get_full_system_prompt(self) -> str:
        """Professional detailed prompt for large models (GPT-4, DeepSeek, Mistral Large)."""
        return """Sei un assistente che genera risposte naturali e complete basate ESCLUSIVAMENTE sui dati forniti.

ISTRUZIONI:
1. Integra tutti i dati disponibili in una risposta coerente
2. Usa un linguaggio naturale e colloquiale in italiano
3. Se alcuni tool sono falliti, menzionalo brevemente
4. Formatta i numeri in modo leggibile (es. 45.234,56 €)
5. Includi tutti i dettagli rilevanti dai dati
6. NON TRONCARE la risposta - completa sempre il discorso
7. Se l'utente richiede una STRUTTURA SPECIFICA per il report (es. sezioni con titoli), segui FEDELMENTE quella struttura.

REGOLE ANTI-ALLUCINAZIONE:
1. **DATE**: Usa SOLO le date che appaiono nei dati. NON inferire o correggere date.
2. **PERSONE**: Menziona SOLO persone che appaiono esplicitamente nei dati.
3. **NON INVENTARE**: Non aggiungere informazioni non presenti nei risultati dei tool.
4. **PERFORMANCE**: Se richiesto, calcola o riporta metriche finanziarie (volatilità, YTD) usando i dati grezzi.

FORMATTAZIONE:
- Titoli ## e ###, grassetti, tabelle Markdown per dati comparativi.
- Per documenti Drive: "Nome" (Link).
- Per email: Mittente, Oggetto, Data."""

    def _build_prompt(
        self,
        query: str,
        results_context: str,
        context: str | None,
        failed: list[ToolResult],
    ) -> str:
        """Build the prompt for the LLM."""
        prompt = f"""Query dell'utente: {query}

Dati raccolti dai tool:
{results_context}"""

        if context:
            prompt = f"Contesto aggiuntivo: {context}\n\n{prompt}"

        if failed:
            failed_list = ", ".join([f"{r.tool_name}" for r in failed])
            prompt += f"\n\nNota: I seguenti tool hanno fallito: {failed_list}"

        prompt += (
            "\n\nGenera una risposta completa e naturale che integri tutti i dati disponibili."
        )

        return prompt

    def _format_results(self, results: list[ToolResult]) -> str:
        """Format tool results for the LLM context.

        Applies compression to keep the payload within LLM context limits:
        - Skips tool results with empty data (empty lists, dicts with only metadata)
        - Deduplicates identical tool calls
        - Truncates individual result JSON to max 4KB
        - Caps total payload at ~120KB
        """
        import json

        MAX_RESULT_CHARS = 8192  # Max chars per single tool result (increased for GWS multi-source)
        MAX_TOTAL_CHARS = 120_000  # Max total chars for all results

        lines: list[str] = []
        seen_data: set[str] = set()  # Deduplicate identical results
        total_chars = 0

        for result in results:
            if result.success and result.data:
                # Skip empty results (empty lists, dicts with only 0 items)
                if self._is_empty_result(result.data):
                    continue

                # Format data
                try:
                    if isinstance(result.data, dict):
                        data_str = json.dumps(result.data, ensure_ascii=False, indent=2)
                    else:
                        data_str = str(result.data)
                except Exception:
                    data_str = str(result.data)

                # Truncate oversized results
                if len(data_str) > MAX_RESULT_CHARS:
                    data_str = data_str[:MAX_RESULT_CHARS] + "\n... [troncato]"

                # Deduplicate identical results from same tool
                dedup_key = f"{result.tool_name}:{data_str[:200]}"
                if dedup_key in seen_data:
                    continue
                seen_data.add(dedup_key)

                entry = f"### {result.tool_name}\n{data_str}"

                # Check total size limit
                if total_chars + len(entry) > MAX_TOTAL_CHARS:
                    lines.append("\n### [NOTA: risultati troncati per limite dimensione]")
                    break

                lines.append(entry)
                total_chars += len(entry)

            elif not result.success:
                lines.append(f"### {result.tool_name}\n[ERRORE: {result.error}]")
                total_chars += 50

        logger.info(
            "format_results_stats",
            total_results=len(results),
            included_results=len(lines),
            total_chars=total_chars,
        )

        return "\n\n".join(lines)

    async def _map_reduce_results(self, results: list[ToolResult], query: str) -> str:
        """MAP: riassumi ogni tool result individualmente, REDUCE: combina i riassunti."""
        successful = [r for r in results if r.success and r.data]
        if not successful:
            return ""

        logger.info("map_reduce_started", total_results=len(successful))

        tasks = []
        for result in successful:
            tasks.append(self._summarize_single_result(result))

        # Esegui i riassunti (MAP phase) in parallelo
        summaries = await asyncio.gather(*tasks, return_exceptions=True)

        lines = []
        for idx, summary in enumerate(summaries):
            tool_name = successful[idx].tool_name
            if isinstance(summary, Exception):
                logger.error("map_result_failed", tool=tool_name, error=str(summary))
                lines.append(f"### {tool_name}\n[Errore nel riassunto dati]")
            else:
                lines.append(f"### {tool_name}\n{summary}")

        logger.info("map_reduce_completed", tool_count=len(lines))
        return "\n\n".join(lines)

    async def _summarize_single_result(self, result: ToolResult) -> str:
        """Riassumi un singolo tool result (MAP step)."""
        import json

        # Prendi i primi 8K chars per non eccedere Qwen context in questa fase
        data_str = json.dumps(result.data, ensure_ascii=False)[:8192]

        prompt = f"""Analizza i dati seguenti provenienti dal tool '{result.tool_name}'. 
RIASSUMI in max 200 parole i dettagli più importanti, mantenendo cifre esatte, nomi e date.
Se è un report finanziario, mantieni i prezzi e le variazioni %.
Se sono email o file, mantieni oggetti, mittenti e link.

DATI DA RIASSUMERE:
{data_str}

RIASSUNTO:"""

        resolved_client, actual_model = resolve_model_client(self._model)
        request = LLMRequest(
            model=actual_model,
            messages=[Message(role="user", content=prompt)],
            temperature=0.1,
            max_tokens=512,
        )

        try:
            # Usiamo il client reasoning (NanoGPT o Qwen Locale) with timeout protection
            import asyncio

            response = await asyncio.wait_for(
                resolved_client.generate_response(request),
                timeout=600.0,  # Increased from 120s for development
            )
            return response.content or data_str[:500]
        except asyncio.TimeoutError:
            logger.warning(
                "summarization_timeout",
                tool=result.tool_name,
                timeout_seconds=600.0,
            )
            return data_str[:500] + " (Timeout - Troncato)"
        except Exception as e:
            logger.warning("summarization_failed", tool=result.tool_name, error=str(e))
            return data_str[:500] + " (Errore - Troncato)"

    @staticmethod
    def _is_empty_result(data: Any) -> bool:
        """Check if a tool result contains no meaningful data."""
        if data is None:
            return True
        if isinstance(data, list) and len(data) == 0:
            return True
        if isinstance(data, dict):
            # Check common list keys — if all lists are empty, it's empty
            list_keys = [
                "results",
                "events",
                "files",
                "messages",
                "emails",
                "items",
                "conferences",
                "documents",
                "attachments",
            ]
            for key in list_keys:
                if key in data:
                    val = data[key]
                    if isinstance(val, list) and len(val) > 0:
                        return False
            # If dict has only metadata keys, treat as empty
            content_keys = set(data.keys()) - {
                "source",
                "timestamp",
                "query",
                "count",
                "total",
                "status",
                "tool_name",
            }
            if not content_keys:
                return True
            # Check if count is explicitly 0
            if data.get("count", -1) == 0 and data.get("total", -1) == 0:
                return True
        return False

    def _fallback_response(self, results: list[ToolResult]) -> str:
        """Generate a human-readable fallback response when LLM fails."""
        successful = [
            r for r in results if r.success and r.data and not self._is_empty_result(r.data)
        ]

        if not successful:
            return "Non sono riuscito a recuperare i dati richiesti."

        parts = ["## 📋 Ecco i dati recuperati\n"]

        for result in successful:
            if not result.data:
                continue

            data = result.data
            tool_name = result.tool_name.replace("google_", "").replace("_", " ").title()

            # Calendar events
            if "calendar" in result.tool_name.lower():
                events = data.get("events", [])
                if events:
                    parts.append(f"### 📅 {tool_name}\n")
                    for event in events[:10]:  # Max 10 events
                        summary = event.get("summary", "Evento senza titolo")
                        start = event.get("start", "")
                        if isinstance(start, dict):
                            start = start.get("dateTime") or start.get("date", "")
                        parts.append(f"- **{summary}** - {start}")
                    parts.append("")

            # Gmail
            elif "gmail" in result.tool_name.lower():
                messages = data.get("messages", [])
                if messages:
                    parts.append(f"### 📧 {tool_name}\n")
                    for msg in messages[:10]:
                        subject = msg.get("subject", "Senza oggetto")
                        sender = msg.get("from", msg.get("sender", ""))
                        date = msg.get("date", "")
                        parts.append(f"- **{subject}** - da {sender} ({date})")
                    parts.append("")

            # Drive
            elif "drive" in result.tool_name.lower():
                files = data.get("files", [])
                if files:
                    parts.append(f"### 📁 {tool_name}\n")
                    for f in files[:10]:
                        name = f.get("name", "File senza nome")
                        link = f.get("webViewLink", "")
                        modified = f.get("modifiedTime", "")[:10] if f.get("modifiedTime") else ""
                        if link:
                            parts.append(f"- **{name}** ([link]({link})) - {modified}")
                        else:
                            parts.append(f"- **{name}** - {modified}")
                    parts.append("")

            # Weather
            elif "weather" in result.tool_name.lower() or "meteo" in result.tool_name.lower():
                parts.append(f"### 🌤️ {tool_name}\n")
                current = data.get("current", data)
                if isinstance(current, dict):
                    temp = current.get("temperature", current.get("temp"))
                    desc = current.get("description", current.get("weather", ""))
                    city = data.get("city", data.get("location", ""))
                    parts.append(f"**{city}**: {temp}°C - {desc}")
                else:
                    parts.append(f"{current}")
                parts.append("")

            # Finance/Crypto - Structured formatting
            elif any(
                x in result.tool_name.lower()
                for x in [
                    "crypto",
                    "stock",
                    "price",
                    "coingecko",
                    "yahoo",
                    "fmp",
                    "finnhub",
                    "binance",
                    "technical",
                    "multi_analysis",
                    "dcf",
                    "key_metrics",
                    "ratios",
                    "income",
                    "balance",
                    "cash_flow",
                    "yahooquery",
                    "fear_greed",
                    "market_context",
                    "alpaca",
                    "edgar",
                    "nasdaq",
                    "fred",
                ]
            ):
                parts.append(f"### 💰 {tool_name}\n")
                if isinstance(data, dict):
                    # Filter out internal/meta keys
                    _skip = {"source", "timestamp", "raw", "maxAge", "symbol"}

                    # Sezione errore (con sanitizzazione API key)
                    err = data.get("error")
                    if err:
                        import re as _re

                        sanitized = _re.sub(
                            r'(api_token|api_key|apikey|token|key)=[^&\s\'"]+',
                            r"\1=***REDACTED***",
                            str(err),
                            flags=_re.IGNORECASE,
                        )
                        parts.append(f"⚠️ {sanitized}\n")
                        continue

                    # Signal/Composite (multi_analysis)
                    if "signal" in data:
                        sig = data.get("signal", "N/A")
                        conf = data.get("confidence", "")
                        score = data.get("score_0_100", "")
                        parts.append(
                            f"🎯 **Signal: {sig}** (confidence: {conf}, score: {score}/100)"
                        )

                    # Trading Levels
                    tl = data.get("trading_levels")
                    if isinstance(tl, dict) and tl:
                        parts.append("\n**🎯 Indicazioni Operative:**")
                        parts.append(f"- 📊 Entry: ${tl.get('entry_price', 'N/A')}")
                        parts.append(f"- 🛑 Stop-Loss: ${tl.get('stop_loss', 'N/A')}")
                        tp1 = tl.get("take_profit_1", "N/A")
                        tp2 = tl.get("take_profit_2", "N/A")
                        tp3 = tl.get("take_profit_3", "N/A")
                        parts.append(f"- ✅ TP1: ${tp1} | TP2: ${tp2} | TP3: ${tp3}")
                        rr = tl.get("risk_reward_ratio", "")
                        parts.append(f"- ⚖️ R:R {rr}")
                        parts.append(f"- 💼 {tl.get('position_sizing', 'Max 2-3% portfolio')}")

                    # Price data
                    price_data = data.get("price")
                    if isinstance(price_data, dict):
                        curr = price_data.get("current") or price_data.get("regularMarketPrice")
                        chg = price_data.get("change_pct", 0)
                        mcap = price_data.get("market_cap")
                        if curr:
                            arrow = "📈" if (chg or 0) > 0 else "📉"
                            parts.append(f"\n**{arrow} Prezzo:** ${curr} ({chg:+.2f}%)")
                        if mcap:
                            parts.append(
                                f"- Market Cap: ${mcap:,.0f}"
                                if isinstance(mcap, (int, float))
                                else f"- Market Cap: {mcap}"
                            )
                    elif data.get("regularMarketPrice") or data.get("price"):
                        p = data.get("regularMarketPrice") or data.get("price")
                        parts.append(f"\n**📊 Prezzo:** ${p}")

                    # Fundamentals
                    fund = data.get("fundamentals") or data.get("financial_kpis")
                    if isinstance(fund, dict):
                        parts.append("\n**📋 Fondamentali:**")
                        _fund_keys = {
                            "pe_forward": "P/E Forward",
                            "peg_ratio": "PEG",
                            "price_to_book": "P/Book",
                            "return_on_equity": "ROE",
                            "profit_margins": "Margine Netto",
                            "debt_to_equity": "D/E",
                            "revenue_growth": "Revenue Growth",
                            "free_cash_flow": "FCF",
                            "recommendation": "Rating",
                        }
                        for k, label in _fund_keys.items():
                            v = fund.get(k)
                            if v is not None:
                                if isinstance(v, float) and abs(v) < 10:
                                    parts.append(
                                        f"- {label}: {v:.2%}"
                                        if abs(v) < 1
                                        else f"- {label}: {v:.2f}"
                                    )
                                else:
                                    parts.append(f"- {label}: {v}")

                    # Technical Indicators
                    tech = data.get("technical_indicators")
                    if isinstance(tech, dict):
                        parts.append("\n**📈 Analisi Tecnica:**")
                        for k, v in tech.items():
                            if isinstance(v, (int, float)):
                                label = k.upper().replace("_", " ")
                                parts.append(
                                    f"- {label}: {v:.2f}"
                                    if isinstance(v, float)
                                    else f"- {label}: {v}"
                                )

                    # Recommendation Trend
                    rec = data.get("recommendation_trend")
                    if isinstance(rec, dict):
                        parts.append("\n**👥 Consensus Analisti:**")
                        sb = rec.get("strong_buy", 0)
                        b = rec.get("buy", 0)
                        h = rec.get("hold", 0)
                        s = rec.get("sell", 0)
                        ss = rec.get("strong_sell", 0)
                        parts.append(
                            f"- Strong Buy: {sb} | Buy: {b} | Hold: {h} | Sell: {s} | Strong Sell: {ss}"
                        )

                    # Breakdown (multi_analysis dimensions)
                    bd = data.get("breakdown")
                    if isinstance(bd, dict):
                        parts.append("\n**📊 Breakdown:**")
                        for dim, dim_data in bd.items():
                            if isinstance(dim_data, dict):
                                sc = dim_data.get("score", 0)
                                pts = dim_data.get("points", [])
                                parts.append(f"- **{dim.title()}** ({sc:+.3f}):")
                                for pt in pts[:3]:
                                    parts.append(f"  {pt}")

                    # Risk flags
                    rf = data.get("risk_flags")
                    if isinstance(rf, list) and rf:
                        parts.append("\n**⚠️ Risk Flags:**")
                        for flag in rf:
                            parts.append(f"- {flag}")

                    # Generic key-value for anything not yet formatted
                    formatted_keys = {
                        "signal",
                        "confidence",
                        "score_0_100",
                        "composite_score",
                        "trading_levels",
                        "price",
                        "fundamentals",
                        "financial_kpis",
                        "technical_indicators",
                        "recommendation_trend",
                        "breakdown",
                        "risk_flags",
                        "error",
                        "name",
                        "extras",
                    }
                    remaining = {
                        k: v
                        for k, v in data.items()
                        if k not in _skip
                        and k not in formatted_keys
                        and isinstance(v, (str, int, float))
                    }
                    if remaining:
                        for k, v in list(remaining.items())[:5]:
                            parts.append(f"- **{k}**: {v}")

                parts.append("")

            # Travel domain - Amadeus, Nager Holidays, OpenSky, ADS-B
            elif any(
                x in result.tool_name.lower()
                for x in [
                    "amadeus",
                    "nager",
                    "holiday",
                    "opensky",
                    "adsb",
                    "aviation",
                    "flight",
                ]
            ):
                parts.append(f"### ✈️ {tool_name}\n")

                # Amadeus errors (configurazione mancante)
                if "error" in data:
                    error_msg = data.get("error", "")
                    hint = data.get("hint", "")
                    if "amadeus" in error_msg.lower() or "amadeus" in result.tool_name.lower():
                        parts.append(f"⚠️ **Amadeus non disponibile**: {error_msg}")
                        if hint:
                            parts.append(f"💡 {hint}")
                    else:
                        parts.append(f"⚠️ {error_msg}")
                    parts.append("")
                    continue

                # Nager Holidays
                if "holiday" in result.tool_name.lower() or "nager" in result.tool_name.lower():
                    holidays = data.get("holidays", [])
                    country = data.get("country", "")
                    year = data.get("year", "")
                    if holidays:
                        parts.append(f"**Festività {country} {year}** ({len(holidays)} giorni)")
                        for h in holidays[:5]:  # Max 5 holidays
                            date = h.get("date", "")
                            name = h.get("localName", h.get("name", ""))
                            parts.append(f"- {date}: {name}")
                        if len(holidays) > 5:
                            parts.append(f"- ... e altre {len(holidays) - 5} festività")
                    parts.append("")
                    continue

                # OpenSky / ADS-B flights
                if "flights" in data or "aircraft" in data:
                    flights = data.get("flights", data.get("aircraft", []))
                    count = data.get("count", len(flights))
                    if flights:
                        parts.append(f"**{count} voli in tempo reale**")
                        for f in flights[:5]:
                            callsign = f.get("callsign", f.get("flight", "N/A")).strip()
                            origin = f.get("origin_country", f.get("dep", ""))
                            dest = f.get("destination", f.get("dest", ""))
                            alt = f.get("altitude", f.get("altitude_ft", ""))
                            parts.append(f"- **{callsign}** - {origin} → {dest} (alt: {alt})")
                    else:
                        parts.append("_Nessun volo trovato in questo momento._")
                    parts.append("")
                    continue

                # Hotel search (Google Places)
                if "hotels" in data:
                    hotels = data.get("hotels", [])
                    city = data.get("city", "")
                    stars = data.get("stars", "")
                    max_price = data.get("max_price", "")

                    header = f"**🏨 Hotel a {city}"
                    if stars:
                        header += f" ({stars}⭐)"
                    if max_price:
                        header += f" - max {max_price}€/notte"
                    header += f"** ({len(hotels)} trovati)"
                    parts.append(header)

                    if hotels:
                        for h in hotels[:8]:
                            name = h.get("name", "Hotel senza nome")
                            rating = h.get("rating", "N/A")
                            reviews = h.get("reviews", 0)
                            price_level = h.get("price_level", "")
                            address = h.get("address", "")

                            rating_str = f"⭐ {rating}" if rating != "N/A" else "⭐ N/A"
                            price_str = f" - {'$' * price_level}" if price_level else ""
                            reviews_str = f" ({reviews} recensioni)" if reviews else ""

                            parts.append(f"- **{name}** {rating_str}{price_str}{reviews_str}")
                            if address:
                                parts.append(f"  📍 {address}")
                    else:
                        parts.append("_Nessun hotel trovato._")
                    parts.append("")
                    continue

                # Restaurant search (Google Places)
                if "restaurants" in data:
                    restaurants = data.get("restaurants", [])
                    city = data.get("city", "")
                    cuisine = data.get("cuisine", "")

                    header = f"**🍽️ Ristoranti a {city}"
                    if cuisine:
                        header += f" - {cuisine}"
                    header += f"** ({len(restaurants)} trovati)"
                    parts.append(header)

                    if restaurants:
                        for r in restaurants[:8]:
                            name = r.get("name", "Ristorante senza nome")
                            rating = r.get("rating", "N/A")
                            reviews = r.get("reviews", 0)
                            price_level = r.get("price_level", "")
                            address = r.get("address", "")

                            rating_str = f"⭐ {rating}" if rating != "N/A" else "⭐ N/A"
                            price_str = f" - {'$' * price_level}" if price_level else ""
                            reviews_str = f" ({reviews} recensioni)" if reviews else ""

                            parts.append(f"- **{name}** {rating_str}{price_str}{reviews_str}")
                            if address:
                                parts.append(f"  📍 {address}")
                    else:
                        parts.append("_Nessun ristorante trovato._")
                    parts.append("")
                    continue

                # Generic travel data
                if isinstance(data, dict):
                    for key, val in list(data.items())[:8]:
                        if key not in ["source", "timestamp", "raw"]:
                            if isinstance(val, (str, int, float)):
                                parts.append(f"- **{key}**: {val}")
                            elif isinstance(val, list) and len(val) > 0:
                                parts.append(f"- **{key}**: {len(val)} elementi")
                parts.append("")

            # Generic fallback
            else:
                parts.append(f"### 📌 {tool_name}\n")
                if isinstance(data, dict):
                    # Show key fields
                    for key, val in list(data.items())[:8]:
                        if key not in ["source", "timestamp", "raw"]:
                            if isinstance(val, (str, int, float)):
                                parts.append(f"- **{key}**: {val}")
                            elif isinstance(val, list) and len(val) > 0:
                                parts.append(f"- **{key}**: {len(val)} elementi")
                elif isinstance(data, str):
                    parts.append(data[:500])
                parts.append("")

        return "\n".join(parts)

    async def synthesize_streaming(
        self,
        query: str,
        results: list[ToolResult],
        context: str | None = None,
        session_id: str | None = None,
    ):
        """Synthesize with streaming output and thinking token extraction.

        Yields chunks of the response as they're generated, with thinking
        tokens extracted and propagated as separate events.

        Thinking detection strategy (in priority order):
        1. Native reasoning field (delta.reasoning) — used by models with built-in
           reasoning support (e.g., Kimi K2.5 :thinking variants)
        2. Explicit <think>...</think> tags — used by Qwen, DeepSeek, and other
           models that wrap reasoning in XML-like tags in the content field
        3. No-tag fallback — if no <think> tag is found within the first few
           tokens, assume the model is not using thinking and treat everything
           as content

        Args:
            query: Original user query
            results: Tool results
            context: Optional context
            session_id: Optional session ID

        Yields:
            StreamChunk with type="thinking" or type="content"
        """
        if not results:
            yield StreamChunk(
                type="content",
                content="Non sono riuscito a recuperare dati per questa richiesta.",
            )
            return

        # Build context
        results_context = self._format_results(results)

        # Apply configured overflow strategy when context exceeds threshold
        if len(results_context) > MAP_THRESHOLD_CHARS:
            strategy = self._get_overflow_strategy()
            logger.info(
                "synthesizer_streaming_overflow_triggered",
                context_size=len(results_context),
                strategy=strategy,
            )

            if strategy == "map_reduce":
                results_context = await self._map_reduce_results(results, query)
            elif strategy == "truncate":
                results_context = self._truncate_context(results_context)
            elif strategy == "cloud_fallback":
                results_context = await self._cloud_fallback_synthesis(results, query)

        failed = [r for r in results if not r.success]
        prompt = self._build_prompt(query, results_context, context, failed)

        # Create streaming request
        resolved_client, actual_model = resolve_model_client(self._model)
        request = LLMRequest(
            model=actual_model,
            messages=[
                Message(role="system", content=self._get_system_prompt()),
                Message(role="user", content=prompt),
            ],
            temperature=0.3,
            max_tokens=16384,
            stream=True,
        )

        try:
            async with asyncio.timeout(600):
                # State machine for thinking extraction
                # States: "detect" -> "thinking" -> "content"
                #   OR:   "detect" -> "content" (no thinking tags found)
                state = "detect"  # Initial state: detecting whether model uses  thinking tags
                detect_buffer = ""  # Buffer for initial detection phase
                think_buffer = ""  # Buffer to handle  tag split across chunks

                # Max chars to buffer while detecting if model uses  thinking tags
                # If we don't see  within this window, assume no thinking
                DETECT_WINDOW = 100

                async for chunk in resolved_client.stream_response(request):
                    if not chunk.choices or not chunk.choices[0].delta:
                        continue

                    delta = chunk.choices[0].delta
                    content = delta.content
                    native_reasoning = delta.reasoning

                    # ── Priority 1: Native reasoning field ──────────────────
                    if native_reasoning:
                        # DEBUG: Log native reasoning chunk size
                        logger.info(
                            "synthesizer_yield_thinking",
                            content_length=len(native_reasoning),
                            session_id=session_id,
                        )
                        yield StreamChunk(
                            type="thinking",
                            content=native_reasoning,
                            thinking=native_reasoning,
                            session_id=session_id,
                            phase="synthesis",
                        )
                        continue

                    if not content:
                        continue

                    # ── State: DETECT ───────────────────────────────────────
                    # Buffer initial tokens to check for <think> tag presence
                    if state == "detect":
                        detect_buffer += content

                        if "<think>" in detect_buffer:
                            # Model uses <think> tags → enter thinking state
                            state = "thinking"
                            # Extract everything after <think> as thinking content
                            after_tag = detect_buffer.split("<think>", 1)[1]

                            # Check if </think> is already in this buffer (very short thinking)
                            if "</think>" in after_tag:
                                thought_part, content_part = after_tag.split("</think>", 1)
                                if thought_part:
                                    yield StreamChunk(
                                        type="thinking",
                                        content=thought_part,
                                        thinking=thought_part,
                                        phase="synthesis",
                                    )
                                state = "content"
                                if content_part.strip():
                                    yield StreamChunk(type="content", content=content_part)
                            else:
                                # Still in thinking, yield what we have
                                if after_tag:
                                    yield StreamChunk(
                                        type="thinking",
                                        content=after_tag,
                                        thinking=after_tag,
                                        phase="synthesis",
                                    )
                        elif len(detect_buffer) > DETECT_WINDOW:
                            # No <think> tag found within detection window
                            # → Model is not using thinking, treat all as content
                            state = "content"
                            yield StreamChunk(type="content", content=detect_buffer)
                        # else: keep buffering in detect state
                        continue

                    # ── State: THINKING ─────────────────────────────────────
                    # Inside <think>...</think> block, yield as thinking until </think>
                    if state == "thinking":
                        # Check for </think> tag, which may be split across chunks
                        # Prepend any leftover from previous chunk
                        text = think_buffer + content
                        think_buffer = ""

                        if "</think>" in text:
                            # Found end of thinking
                            thought_part, content_part = text.split("</think>", 1)
                            if thought_part:
                                yield StreamChunk(
                                    type="thinking",
                                    content=thought_part,
                                    thinking=thought_part,
                                    phase="synthesis",
                                )
                            state = "content"
                            if content_part.strip():
                                yield StreamChunk(type="content", content=content_part)
                        elif text.endswith(
                            ("<", "</", "</t", "</th", "</thi", "</thin", "</think")
                        ):
                            # Partial </think> tag at end of chunk — buffer it
                            # Find the start of the potential partial tag
                            for i in range(min(8, len(text)), 0, -1):
                                suffix = text[-i:]
                                if "</think>".startswith(suffix):
                                    think_buffer = suffix
                                    safe_part = text[:-i]
                                    if safe_part:
                                        yield StreamChunk(
                                            type="thinking",
                                            content=safe_part,
                                            thinking=safe_part,
                                            phase="synthesis",
                                        )
                                    break
                            else:
                                # No partial match, yield everything
                                yield StreamChunk(
                                    type="thinking",
                                    content=text,
                                    thinking=text,
                                    phase="synthesis",
                                )
                        else:
                            # Normal thinking content
                            yield StreamChunk(
                                type="thinking",
                                content=text,
                                thinking=text,
                                phase="synthesis",
                            )
                        continue

                    # ── State: CONTENT ──────────────────────────────────────
                    # Normal content phase — yield directly
                    if state == "content":
                        yield StreamChunk(type="content", content=content)

                # End of stream: flush any remaining buffers
                if state == "detect" and detect_buffer:
                    # Never found <think> tag, entire output is content
                    yield StreamChunk(type="content", content=detect_buffer)
                elif state == "thinking" and think_buffer:
                    # Stream ended inside thinking (incomplete </think> tag)
                    yield StreamChunk(
                        type="thinking",
                        content=think_buffer,
                        thinking=think_buffer,
                        phase="synthesis",
                    )

                # DEBUG: Log final streaming stats
                logger.info(
                    "synthesizer_streaming_complete",
                    query_preview=query[:50],
                    tools_used=len([r for r in results if r.success]),
                    tools_failed=len(failed),
                    final_state=state,
                )

        except TimeoutError:
            logger.error(
                "synthesizer_streaming_timeout",
                timeout_seconds=600,
                results_count=len(results),
                prompt_size_kb=round(len(prompt) / 1024, 1),
            )
            yield StreamChunk(type="content", content=self._fallback_response(results))

        except Exception as e:
            import traceback

            logger.error(
                "synthesizer_streaming_failed",
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
                results_count=len(results),
                prompt_size_kb=round(len(prompt) / 1024, 1),
            )
            yield StreamChunk(type="content", content=self._fallback_response(results))
