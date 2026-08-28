"""
CSV file validation — type checks and size cap.

L2.1 implementation.
Max file size: MAX_FILE_SIZE_MB from settings (default 5 MB).
Allowed extensions: .csv only for lean scope.
"""
from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

ALLOWED_EXTENSIONS = {".csv"}
# Some systems send text/csv, others text/plain — allow both.
ALLOWED_MIME_TYPES = {"text/csv", "text/plain", "application/csv",
                      "application/vnd.ms-excel", "application/octet-stream"}


async def validate_csv_upload(file: UploadFile) -> bytes:
    """
    Validate an uploaded file and return its raw bytes.

    Checks:
      1. File has a .csv extension.
      2. Content-Type is in the allow list (best-effort; browsers vary).
      3. File size ≤ MAX_FILE_SIZE_MB.

    Returns raw bytes on success.
    Raises HTTPException 400/413 on validation failure.
    """
    # 1 — Extension check
    filename = file.filename or ""
    ext = filename[filename.rfind("."):].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only CSV files are supported. Got extension: '{ext or '(none)' }'",
        )

    # 2 — MIME type (best effort — browsers are inconsistent)
    content_type = (file.content_type or "").lower()
    if content_type and content_type not in ALLOWED_MIME_TYPES:
        logger.warning("Unexpected MIME type '%s' for file '%s'", content_type, filename)
        # Don't reject — extension is the canonical check. Just log.

    # 3 — Size check. Read entire file into memory (max 5 MB is fine).
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    raw = await file.read()
    if len(raw) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large: {len(raw):,} bytes "
                   f"(limit: {settings.max_file_size_mb} MB).",
        )

    if len(raw) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty.",
        )

    logger.info("CSV validated: '%s', %d bytes", filename, len(raw))
    return raw
