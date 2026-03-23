"""Session Title Generation - Auto-naming for chat sessions.

Genera titoli descrittivi (3-5 parole) per le sessioni chat
basati sulla query iniziale dell'utente.
"""

import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field

from me4brain.llm.config import get_llm_config
from me4brain.llm.dynamic_client import DynamicLLMClient
from me4brain.llm.models import LLMRequest, Message
from me4brain.llm.provider_registry import ProviderType

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/sessions", tags=["Session"])

# Prompt di sistema per la generazione dei titoli
TITLE_GENERATION_SYSTEM_PROMPT = """You are a session title generator. Generate a short, descriptive title of exactly 3-5 words that summarizes the user's query. Respond ONLY with the title text, no explanation, no punctuation, no quotes. The title should be in the user's language (Italian if the query is in Italian, English otherwise)."""

# Costanti
MAX_PROMPT_LENGTH = 2000
MAX_TITLE_LENGTH = 50
DEFAULT_TIMEOUT = 30.0  # secondi - aumentato per modelli thinking qwen3.5


class GenerateTitleRequest(BaseModel):
    """Request per la generazione del titolo."""

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=MAX_PROMPT_LENGTH,
        description="Primo messaggio dell'utente per generare il titolo",
    )


class GenerateTitleResponse(BaseModel):
    """Response con il titolo generato."""

    title: str = Field(
        ...,
        max_length=MAX_TITLE_LENGTH,
        description="Titolo generato (3-5 parole)",
    )


def _build_title_request(prompt: str) -> LLMRequest:
    """Costruisce la request LLM per la generazione del titolo."""
    return LLMRequest(
        messages=[
            Message(role="system", content=TITLE_GENERATION_SYSTEM_PROMPT),
            Message(role="user", content=prompt),
        ],
        model="",  # Viene impostato dal client
        max_tokens=2000,  # Aumentato per modelli thinking - deve contenere sia reasoning che titolo
        temperature=0.3,
    )


def _parse_title(response_content: str | None) -> str | None:
    """Parse della risposta LLM per estrarre il titolo.

    Gestisce sia risposte dirette che contenuti di reasoning (modelli qwen3.5).
    Per reasoning content, il titolo appare tipicamente alla fine dopo "with" o simili.
    """
    if not response_content:
        return None

    # Pulisci la risposta: rimuovi spazi multipli, newline, etc
    content = response_content.strip()

    # Rimuovi eventuali virgolette
    content = content.strip("\"'")

    # Verifica che non sia vuoto
    if not content:
        return None

    # Se il contenuto è già entro i limiti, usalo direttamente
    if len(content) <= MAX_TITLE_LENGTH:
        title = content
    else:
        # Per contenuti lunghi (reasoning), estrai il titolo dalla fine
        # I modelli thinking terminano spesso con frasi come "with 'Title'" o "with Title"
        # o frasi come "Selection: Title"
        title = _extract_title_from_reasoning(content)
        if not title:
            # Ultimo tentativo: prendi le ultime parole
            words = content.split()
            if len(words) <= 6:  # Allow slightly more words for reasoning extraction
                title = " ".join(words[-6:])
            else:
                return None

    # Validazione finale
    if not title or len(title) > MAX_TITLE_LENGTH:
        return None

    # Verifica che contenga almeno una parola significativa
    words = title.split()
    if len(words) < 1 or all(len(w) < 2 for w in words):
        return None

    return title


def _extract_title_from_reasoning(reasoning_content: str) -> str | None:
    """Estrae il titolo dal content di reasoning dei modelli qwen3.5.

    I modelli thinking terminano con il titolo alla fine, spesso dopo
    frasi come "with", "Selection:", "Go with", etc.
    """
    import re

    # Pattern comuni per trovare il titolo alla fine del reasoning
    patterns = [
        # "with 'Title'" or 'with Title' or "with Title"
        r"with\s+[\"']([^\"']+)[\"']",
        # "with Title" (no quotes)
        r"with\s+([A-Za-z0-9\s\-,]+?)(?:\"|\'|$|\n)",
        # "Selection: Title"
        r"[Ss]election:\s*([A-Za-z0-9\s\-,]+?)(?:\"|\'|$|\n)",
        # "Let's go with Title" or "Let's try with Title"
        r"[Ll]et'?s\s+(?:go\s+with|try\s+with)\s+([A-Za-z0-9\s\-,]+?)(?:\"|\'|$|\n)",
        # "final choice: Title" or "final title: Title"
        r"(?:final\s+(?:choice|title):\s*)([\"']?[\w\s\-,]+?[\"']?)(?:\"|\'|$|\n)",
    ]

    for pattern in patterns:
        match = re.search(pattern, reasoning_content)
        if match:
            candidate = match.group(1).strip()
            # Pulisci il candidato
            candidate = re.sub(r"^\"|\'|\"$|\'$", "", candidate)  # Rimuovi virgolette
            candidate = candidate.strip()
            # Verifica che sia ragionevole (non troppo lungo, non troppo corto)
            if 3 <= len(candidate) <= MAX_TITLE_LENGTH:
                return candidate

    # Fallback: prendi l'ultima riga non vuota e parsala
    lines = [line.strip() for line in reasoning_content.split("\n") if line.strip()]
    if lines:
        last_line = lines[-1]
        # Rimuovi prefissi comuni
        last_line = re.sub(r"^(?:\d+\.\s*|\-\s*|\*\s*)+", "", last_line)
        last_line = last_line.strip("\"'")
        if 3 <= len(last_line) <= MAX_TITLE_LENGTH:
            return last_line

    return None


async def generate_session_title(prompt: str, timeout: float = DEFAULT_TIMEOUT) -> str | None:
    """Genera un titolo per la sessione usando l'LLM.

    Args:
        prompt: Il primo messaggio dell'utente.
        timeout: Timeout in secondi per la chiamata LLM.

    Returns:
        Il titolo generato, o None se la generazione fallisce.
    """
    config = get_llm_config()

    try:
        # Usa il modello di routing come default, ma allow override
        model = getattr(config, "model_title_generation", None) or config.model_routing

        client = DynamicLLMClient(
            base_url=config.ollama_base_url,
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            default_model=model,
            timeout=timeout,
        )

        request = _build_title_request(prompt)
        response = await client.generate_response(request)

        title = _parse_title(response.content)
        if title:
            logger.info("session_title_generated", title=title, prompt_length=len(prompt))
        else:
            logger.warning("session_title_parse_failed", raw_response=response.content)

        return title

    except TimeoutError:
        logger.warning("session_title_timeout", timeout=timeout)
        return None
    except Exception as e:
        logger.error("session_title_generation_failed", error=str(e), error_type=type(e).__name__)
        return None


@router.post(
    "/generate-title",
    response_model=GenerateTitleResponse,
    summary="Genera titolo sessione",
    description="Genera un titolo descrittivo per una nuova sessione basato sulla query iniziale.",
)
async def generate_title_endpoint(
    request: GenerateTitleRequest,
) -> GenerateTitleResponse:
    """Endpoint per generare titoli delle sessioni.

    Usa l'LLM configurato per generare un titolo di 3-5 parole
    che riassume la query dell'utente.
    """
    title = await generate_session_title(request.prompt)

    if not title:
        # Fallback: usa i primi 47 caratteri del prompt + "..." (totale 50)
        if len(request.prompt) > MAX_TITLE_LENGTH:
            title = request.prompt[: MAX_TITLE_LENGTH - 3].strip() + "..."
        else:
            title = request.prompt.strip()

        # Rimuovi spazi multipli causati da truncation
        title = " ".join(title.split())

    return GenerateTitleResponse(title=title)
