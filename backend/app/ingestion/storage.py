"""
Supabase Storage helpers — upload/fetch raw CSV files.

L2.1 implementation.
Bucket: 'files' (private, created in Step 1 via Supabase Dashboard).
Storage path convention: {workspace_id}/{content_hash}/{filename}
"""
from app.core.logging import get_logger
from app.core.supabase_client import service_client

logger = get_logger(__name__)

BUCKET = "files"


def upload_file(
    workspace_id: str,
    content_hash: str,
    filename: str,
    data: bytes,
) -> str:
    """
    Upload raw bytes to Supabase Storage.

    Returns the storage path (used as the `storage_path` column in the
    `files` table). Raises on failure.
    """
    storage_path = f"{workspace_id}/{content_hash}/{filename}"
    try:
        service_client().storage.from_(BUCKET).upload(
            path=storage_path,
            file=data,
            file_options={"content-type": "text/csv", "upsert": "true"},
        )
    except Exception as exc:
        logger.error("Storage upload failed path=%s err=%s", storage_path, exc)
        raise
    logger.info("Storage upload OK path=%s bytes=%d", storage_path, len(data))
    return storage_path


def fetch_file(storage_path: str) -> bytes:
    """Download raw bytes from Supabase Storage by storage_path."""
    return service_client().storage.from_(BUCKET).download(storage_path)
