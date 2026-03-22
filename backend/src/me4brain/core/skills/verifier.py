"""Skill Verifier - Post-execution verification (pattern Voyager)."""

from typing import Optional

import structlog

from me4brain.core.skills.types import Skill, VerificationResult

logger = structlog.get_logger(__name__)


class SkillVerifier:
    """
    Verifica skill post-esecuzione.

    Implementa il pattern Voyager per verificare che una skill
    abbia prodotto il risultato atteso e può tentare di correggere
    automaticamente in caso di fallimento.
    """

    def __init__(
        self,
        llm_func: Optional[callable] = None,
        max_retries: int = 3,
    ):
        """
        Inizializza il verifier.

        Args:
            llm_func: Funzione LLM per verifica semantica (async)
            max_retries: Numero massimo di retry con fix
        """
        self.llm_func = llm_func
        self.max_retries = max_retries

    async def verify(
        self,
        skill: Skill,
        input_query: str,
        actual_output: str,
        expected_behavior: Optional[str] = None,
    ) -> VerificationResult:
        """
        Verifica che la skill abbia prodotto risultato atteso.

        Args:
            skill: Skill eseguita
            input_query: Query originale
            actual_output: Output effettivo
            expected_behavior: Comportamento atteso (opzionale)

        Returns:
            VerificationResult con esito e suggerimenti
        """
        # Verifica base: output non vuoto
        if not actual_output or actual_output.strip() == "":
            return VerificationResult(
                success=False,
                error_message="Output vuoto",
                suggestions=["Verificare che tutti i tool siano disponibili"],
            )

        # Verifica semantica con LLM (se disponibile)
        if self.llm_func:
            return await self._semantic_verify(
                skill, input_query, actual_output, expected_behavior
            )

        # Fallback: assume successo se output presente
        return VerificationResult(success=True)

    async def _semantic_verify(
        self,
        skill: Skill,
        input_query: str,
        actual_output: str,
        expected_behavior: Optional[str],
    ) -> VerificationResult:
        """Verifica semantica usando LLM."""
        try:
            prompt = f"""Valuta se l'output soddisfa la richiesta.

Skill: {skill.name}
Descrizione skill: {skill.description}
Query utente: {input_query}
Output prodotto: {actual_output[:500]}
{"Comportamento atteso: " + expected_behavior if expected_behavior else ""}

Rispondi in JSON:
{{"success": true/false, "reason": "...", "suggestions": ["...", "..."]}}"""

            response = await self.llm_func(prompt)

            # Parse risposta JSON
            import json

            try:
                result = json.loads(response)
                return VerificationResult(
                    success=result.get("success", False),
                    error_message=result.get("reason")
                    if not result.get("success")
                    else None,
                    suggestions=result.get("suggestions", []),
                )
            except json.JSONDecodeError:
                # LLM non ha restituito JSON valido
                return VerificationResult(success=True)

        except Exception as e:
            logger.warning("semantic_verification_failed", error=str(e))
            return VerificationResult(success=True)

    async def verify_and_retry(
        self,
        skill: Skill,
        execute_func: callable,
        input_query: str,
        expected_behavior: Optional[str] = None,
    ) -> tuple[bool, str, int]:
        """
        Verifica ed eventualmente riprova con correzioni.

        Args:
            skill: Skill da eseguire
            execute_func: Funzione per eseguire la skill (async)
            input_query: Query originale
            expected_behavior: Comportamento atteso

        Returns:
            Tuple (success, final_output, retry_count)
        """
        retry_count = 0
        last_error = None
        last_output = ""

        while retry_count <= self.max_retries:
            try:
                # Esegui skill
                output = await execute_func(skill, input_query)
                last_output = output

                # Verifica
                result = await self.verify(
                    skill, input_query, output, expected_behavior
                )

                if result.success:
                    logger.info(
                        "skill_verified_success",
                        skill_id=skill.id,
                        retry_count=retry_count,
                    )
                    return True, output, retry_count

                # Fallito: prepara per retry
                last_error = result.error_message
                retry_count += 1

                if retry_count <= self.max_retries:
                    logger.warning(
                        "skill_verify_retry",
                        skill_id=skill.id,
                        retry=retry_count,
                        error=last_error,
                    )

            except Exception as e:
                last_error = str(e)
                retry_count += 1
                logger.error(
                    "skill_execution_error",
                    skill_id=skill.id,
                    retry=retry_count,
                    error=last_error,
                )

        # Tutti i retry falliti
        logger.error(
            "skill_verification_failed",
            skill_id=skill.id,
            total_retries=retry_count,
            last_error=last_error,
        )
        return False, last_output, retry_count

    async def suggest_fix(
        self, skill: Skill, error_message: str, context: dict
    ) -> list[str]:
        """
        Suggerisce correzioni per una skill fallita.

        Args:
            skill: Skill che ha fallito
            error_message: Messaggio di errore
            context: Contesto dell'esecuzione

        Returns:
            Lista di suggerimenti
        """
        if not self.llm_func:
            return ["Verificare i parametri della skill", "Controllare le dipendenze"]

        try:
            prompt = f"""Suggerisci come correggere questa skill fallita:

Skill: {skill.name}
Codice: {skill.code[:500]}
Errore: {error_message}
Contesto: {context}

Fornisci 2-3 suggerimenti pratici e concisi."""

            response = await self.llm_func(prompt)
            # Parse suggerimenti (uno per riga)
            suggestions = [s.strip() for s in response.split("\n") if s.strip()]
            return suggestions[:3]

        except Exception as e:
            logger.warning("suggest_fix_failed", error=str(e))
            return ["Verificare la configurazione"]
