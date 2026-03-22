"""Entity Extraction Utilities - Estrazione entità centralizzata.

Fornisce funzioni per estrarre entità tipizzate dall'analisi LLM.
TUTTI i domain handler devono usare queste funzioni invece di parsing manuale.

Pattern:
    analysis = await analyze_query(query, ...)  # LLM estrae entities
    city = get_entity_by_type(analysis, "location")  # Handler estrae entità

Tipi entità supportati:
- location: città, paesi, indirizzi
- financial_instrument: ticker azionari, crypto
- organization: aziende, squadre, enti
- person: nomi persone
- date_range: periodi temporali
- query_text: testo da cercare
"""

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def get_entity_by_type(
    analysis: dict[str, Any] | None,
    entity_type: str,
    default: str | None = None,
) -> str | None:
    """Estrae un'entità per tipo dall'analisi LLM.

    Args:
        analysis: Risultato di analyze_query() con campo "entities"
        entity_type: Tipo entità da cercare (location, financial_instrument, etc.)
        default: Valore di default se entità non trovata

    Returns:
        Valore dell'entità o default

    Example:
        >>> analysis = {"entities": [{"type": "location", "value": "Caltanissetta"}]}
        >>> get_entity_by_type(analysis, "location")
        'Caltanissetta'
    """
    if not analysis:
        return default

    entities = analysis.get("entities", [])

    for entity in entities:
        # Nuovo formato strutturato: {"type": "location", "value": "Caltanissetta"}
        if isinstance(entity, dict):
            if entity.get("type") == entity_type:
                value = entity.get("value")
                if value:
                    logger.debug("entity_extracted", type=entity_type, value=value)
                    return str(value).strip()

        # Legacy format: ["Caltanissetta"] - assume prima stringa è location
        elif isinstance(entity, str) and entity_type == "location":
            logger.debug("entity_extracted_legacy", value=entity)
            return entity.strip()

    logger.debug("entity_not_found", type=entity_type, default=default)
    return default


def get_all_entities_by_type(
    analysis: dict[str, Any] | None,
    entity_type: str,
) -> list[str]:
    """Estrae TUTTE le entità di un tipo dall'analisi LLM."""
    if not analysis:
        return []

    entities = analysis.get("entities", [])
    results = []

    for entity in entities:
        if isinstance(entity, dict) and entity.get("type") == entity_type:
            value = entity.get("value")
            if value:
                results.append(str(value).strip())

    return results


def get_query_text(analysis: dict[str, Any] | None, default: str = "") -> str:
    """Estrae il testo da cercare dall'analisi (per Drive, Gmail, etc.)."""
    return get_entity_by_type(analysis, "query_text", default) or default


# =============================================================================
# Robust Entity Extraction (ReAct Architecture)
# =============================================================================

# Stopwords italiane che possono essere erroneamente estratte come ticker
ITALIAN_STOPWORDS = {
    "di",
    "il",
    "la",
    "le",
    "un",
    "una",
    "che",
    "per",
    "con",
    "su",
    "da",
    "del",
    "della",
    "dei",
    "delle",
    "al",
    "alla",
    "ai",
    "alle",
    "nel",
    "nella",
    "nei",
    "nelle",
    "sul",
    "sulla",
    "sui",
    "sulle",
    "dal",
    "dalla",
    "dai",
    "dalle",
    "a",
    "e",
    "i",
    "o",
    "ma",
    "se",
    "no",
    "si",
    "come",
    "questo",
    "quella",
    "sono",
    "ha",
    "ho",
    "fa",
    "va",
    "io",
    "tu",
    "lui",
    "lei",
    "noi",
    "voi",
    "loro",
    "mio",
    "tuo",
    "suo",
    "mia",
    "tua",
    "sua",
    "anche",
    "ancora",
    "poi",
    "essere",
    "avere",
    "fare",
    "andare",
    "cosa",
    "dove",
    "quando",
    "perche",
}


def robust_entity_extraction(
    query: str,
    llm_entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Valida e corregge entità estratte dall'LLM.

    Risolve problemi comuni:
    - Stopwords italiane estratte come ticker (es. "DI", "IL")
    - Ticker non validi (troppo corti, non uppercase)
    - Entità vuote o nulle

    Args:
        query: Query originale per context
        llm_entities: Entità estratte dall'LLM

    Returns:
        Lista entità validate e pulite
    """
    import re

    validated = []

    for entity in llm_entities:
        if not isinstance(entity, dict):
            continue

        etype = entity.get("type", "")
        value = entity.get("value", "")

        if not etype or not value:
            continue

        # =====================================================================
        # Validazione per tipo
        # =====================================================================

        # Financial instruments (ticker symbols)
        if etype == "financial_instrument":
            value_upper = str(value).upper().strip()

            # Skip Italian stopwords erroneamente estratte come ticker
            if value_upper.lower() in ITALIAN_STOPWORDS:
                logger.debug(
                    "entity_filtered_stopword", type=etype, value=value, reason="Italian stopword"
                )
                continue

            # Ticker deve essere 2-5 caratteri uppercase alfanumerici
            if not re.match(r"^[A-Z]{2,5}$", value_upper):
                # Check se è un nome azienda invece di ticker
                if len(value) > 8 or " " in value:
                    # Potrebbe essere nome azienda, lascia passare
                    pass
                else:
                    logger.debug(
                        "entity_filtered_invalid_ticker",
                        type=etype,
                        value=value,
                        reason="Invalid ticker format",
                    )
                    continue

        # Person type - skip if too generic
        if etype == "person":
            if value.lower() in {"giocatori", "giocatore", "players", "player"}:
                logger.debug(
                    "entity_filtered_generic",
                    type=etype,
                    value=value,
                    reason="Too generic, not a specific person",
                )
                continue

        # Location - basic validation
        if etype == "location":
            if len(value) < 2:
                continue

        # Add validated entity
        validated.append(entity)

    logger.debug(
        "entity_validation_complete",
        original_count=len(llm_entities),
        validated_count=len(validated),
    )

    return validated
