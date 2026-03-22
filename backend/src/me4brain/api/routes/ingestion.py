"""Ingestion API Routes - File Upload & OCR Processing.

Espone HybridOCRService via HTTP per upload e processing di documenti.
"""

import tempfile
from pathlib import Path
from typing import Annotated

import structlog
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from me4brain.ingestion.ocr import HybridOCRService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/ingestion", tags=["Ingestion"])

# Lazy-load OCR service (singleton)
_ocr_service: HybridOCRService | None = None


def get_ocr_service() -> HybridOCRService:
    """Get or create OCR service instance."""
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = HybridOCRService()
        logger.info("ocr_service_initialized")
    return _ocr_service


# Constants
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".bmp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


class OCRResponse(BaseModel):
    """Response from OCR processing."""

    filename: str = Field(..., description="Original filename")
    content: str = Field(..., description="Extracted text content")
    method: str = Field(..., description="Extraction method used (native_pdf, vision_llm, error)")
    model: str | None = Field(None, description="Model used for vision OCR")
    pages: int = Field(..., description="Number of pages processed")
    reasoning: str | None = Field(None, description="Reasoning from vision model (if applicable)")


@router.post("/upload", response_model=OCRResponse)
async def upload_file(
    file: Annotated[UploadFile, File(..., description="File to process (PDF or image)")],
) -> OCRResponse:
    """
    Upload and process a file with OCR.

    Supports: PDF, JPEG, PNG, BMP (max 10MB)

    Strategy:
    1. Native PDF extraction (fast path) - uses pypdf for text-based PDFs
    2. Vision LLM fallback (smart path) - uses Kimi K2.5 for scanned PDFs and images

    Returns:
        OCRResponse with extracted content and metadata
    """
    # Validate filename
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Validate extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Read file content
    content = await file.read()

    # Validate file size
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // 1024 // 1024}MB",
        )

    # Save to temp file for processing
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        # Process with HybridOCRService
        ocr = get_ocr_service()
        result = await ocr.process_file(tmp_path)

        logger.info(
            "file_processed",
            filename=file.filename,
            method=result.get("method"),
            content_length=len(result.get("content", "")),
        )

        return OCRResponse(
            filename=file.filename,
            content=result.get("content", ""),
            method=result.get("method", "unknown"),
            model=result.get("model"),
            pages=result.get("pages", 0),
            reasoning=result.get("reasoning"),
        )

    except Exception as e:
        logger.error("file_processing_failed", filename=file.filename, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}") from e

    finally:
        # Cleanup temp file
        from contextlib import suppress

        with suppress(Exception):
            tmp_path.unlink()


@router.get("/health")
async def ingestion_health():
    """Health check for ingestion service."""
    try:
        ocr = get_ocr_service()
        return {
            "status": "ok",
            "service": "ingestion",
            "ocr_available": True,
            "vision_model": ocr.vision_model,
        }
    except Exception as e:
        return {
            "status": "degraded",
            "service": "ingestion",
            "ocr_available": False,
            "error": str(e),
        }
