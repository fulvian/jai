"""
Servizio OCR Ibrido per Me4BrAIn.

Strategia:
1. Tentativo Locale (Fast Path): Estrazione testo nativo da PDF via pypdf.
2. Fallback Vision (Smart Path): Se il testo è insufficiente (PDF scansionato) o è un'immagine,
   usa NanoGPT con modello Vision (Kimi K2.5) per analisi multimodale.
"""

import base64
import io
from pathlib import Path
from typing import Optional

import pypdf
from pdf2image import convert_from_bytes
from structlog import get_logger

from me4brain.llm import (
    LLMRequest,
    Message,
    MessageContent,
    NanoGPTClient,
    get_llm_config,
)

log = get_logger()


class HybridOCRService:
    """Gestisce l'estrazione testo ibrida (Locale + Vision AI)."""

    def __init__(self):
        self.config = get_llm_config()
        self.client = NanoGPTClient(
            api_key=self.config.nanogpt_api_key,
            base_url=self.config.nanogpt_base_url,
        )
        self.vision_model = self.config.model_vision  # Kimi K2.5 Thinking

    async def process_file(self, file_path: Path) -> dict:
        """
        Processa un file e restituisce il contenuto estratto e i metadati.

        Returns:
            dict: {
                "content": str,
                "method": "native_pdf" | "vision_llm",
                "model": str | None,
                "pages": int
            }
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        mime_type = self._get_mime_type(file_path)
        log.info("Processing file", file=file_path.name, mime=mime_type)

        # 1. Path PDF Nativo
        if mime_type == "application/pdf":
            text, pages = self._extract_native_pdf(file_path)
            # Euristica: se abbiamo estratto abbastanza testo (>50 char/page), assumiamo sia nativo
            if text and len(text) / max(pages, 1) > 50:
                log.info("Native PDF text extracted", pages=pages, length=len(text))
                return {"content": text, "method": "native_pdf", "model": "pypdf", "pages": pages}
            log.info("Low text density in PDF, switching to Vision OCR", text_len=len(text or ""))

        # 2. Path Vision (Immagini o PDF Scansionati)
        return await self._analyze_with_vision(file_path, mime_type)

    def _extract_native_pdf(self, file_path: Path) -> tuple[Optional[str], int]:
        """Estrae testo da PDF usando pypdf locale."""
        try:
            reader = pypdf.PdfReader(file_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n\n"
            return text.strip(), len(reader.pages)
        except Exception as e:
            log.warning("PDF native extraction failed", error=str(e))
            return None, 0

    async def _analyze_with_vision(self, file_path: Path, mime_type: str) -> dict:
        """Usa Kimi K2.5 per analizzare visivamente il documento."""
        images_b64 = []

        # Gestione input: Immagine vs PDF
        if mime_type == "application/pdf":
            # Converte prima pagina PDF in immagine (PoC: solo prima pagina per ora per vision)
            # TODO: Gestire multi-pagina iterando o facendo collage
            try:
                images = convert_from_bytes(file_path.read_bytes(), first_page=1, last_page=1)
                if not images:
                    raise ValueError("Could not convert PDF to image")

                # Converti PIL in base64
                img_byte_arr = io.BytesIO()
                images[0].save(img_byte_arr, format="JPEG")
                img_b64 = base64.b64encode(img_byte_arr.getvalue()).decode("utf-8")
                images_b64.append(f"data:image/jpeg;base64,{img_b64}")
                pages = 1  # Analizziamo 1 pag per ora nel path vision fallback
            except Exception as e:
                return {
                    "content": f"Vision Conversion Error: {e}",
                    "method": "error",
                    "model": None,
                    "pages": 0,
                }

        elif mime_type.startswith("image/"):
            # Leggi immagine diretta
            img_b64 = base64.b64encode(file_path.read_bytes()).decode("utf-8")
            images_b64.append(f"data:{mime_type};base64,{img_b64}")
            pages = 1

        else:
            return {
                "content": "Unsupported file type",
                "method": "error",
                "model": None,
                "pages": 0,
            }

        # Costruisci richiesta LLM
        log.info(f"Sending to Vision Model: {self.vision_model}")

        content_parts = [
            MessageContent(
                type="text",
                text="Esegui OCR accurato e analisi del documento. Estrai tutto il testo visibile e descrivi la struttura/layout se rilevante.",
            )
        ]

        for img_data in images_b64:
            content_parts.append(MessageContent(type="image_url", image_url={"url": img_data}))

        request = LLMRequest(
            model=self.vision_model,
            messages=[Message(role="user", content=content_parts)],
            max_tokens=2000,  # Kimi ha 256k context, possiamo essere generosi
        )

        try:
            response = await self.client.generate_response(request)
            return {
                "content": response.content,
                "reasoning": response.reasoning,
                "method": "vision_llm",
                "model": self.vision_model,
                "pages": pages,
            }
        except Exception as e:
            log.error("Vision API failed", error=str(e))
            return {
                "content": f"Vision API Error: {str(e)}",
                "method": "error",
                "model": self.vision_model,
                "pages": 0,
            }

    def _get_mime_type(self, path: Path) -> str:
        if path.suffix.lower() == ".pdf":
            return "application/pdf"
        if path.suffix.lower() in [".jpg", ".jpeg"]:
            return "image/jpeg"
        if path.suffix.lower() == ".png":
            return "image/png"
        if path.suffix.lower() == ".bmp":
            return "image/bmp"
        return "application/octet-stream"
