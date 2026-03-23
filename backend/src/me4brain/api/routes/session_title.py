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
DEFAULT_TIMEOUT = 5.0  # secondi


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
        max_tokens=20,
        temperature=0.3,
    )


def _parse_title(response_content: str | None) -> str | None:
    """Parse della risposta LLM per estrarre il titolo."""
    if not response_content:
        return None

    # Pulisci la risposta: rimuovi spazi multipli, newline, etc
    title = response_content.strip()

    # Rimuovi eventuali virgolette
    title = title.strip("\"'")

    # Verifica che il titolo sia ragionevole (non troppo lungo, non vuoto)
    if not title or len(title) > MAX_TITLE_LENGTH:
        return None

    # Verifica che contenga almeno una parola significativa
    words = title.split()
    if len(words) < 1 or all(len(w) < 2 for w in words):
        return None

    return title


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
