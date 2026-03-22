"""File upload endpoint with OCR processing."""

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter()

# Lazy import to avoid circular dependencies
_ocr_service = None


def get_ocr_service():
    """Lazy-load HybridOCRService from Me4BrAIn."""
    global _ocr_service
    if _ocr_service is None:
        try:
            from me4brain.ingestion.ocr import HybridOCRService

            _ocr_service = HybridOCRService()
        except ImportError as e:
            raise HTTPException(status_code=500, detail=f"OCR service not available: {e}")
    return _ocr_service


ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".bmp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload and process a file with OCR.

    Supports: PDF, JPEG, PNG, BMP
    Uses Me4BrAIn HybridOCRService (native + Vision LLM fallback)

    Returns:
        {
            "filename": str,
            "content": str (extracted text),
            "method": "native_pdf" | "vision_llm" | "error",
            "model": str | None,
            "pages": int
        }
    """
    # Validate file extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

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
        # Process with Me4BrAIn OCR
        ocr = get_ocr_service()
        result = await ocr.process_file(tmp_path)

        return {
            "filename": file.filename,
            "content": result.get("content", ""),
            "method": result.get("method", "unknown"),
            "model": result.get("model"),
            "pages": result.get("pages", 0),
        }

    finally:
        # Cleanup temp file
        try:
            tmp_path.unlink()
        except Exception:
            pass
