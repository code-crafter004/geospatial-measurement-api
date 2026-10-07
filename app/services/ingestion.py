import uuid
import zipfile
from pathlib import Path

from fastapi import UploadFile

from app.config import settings
from app.core.errors import AppError

ALLOWED_TYPES = {".zip": "shapefile_zip", ".kml": "kml"}


def save_upload(upload: UploadFile) -> tuple[str, str, Path]:
    """Validate and store an upload. Returns (filename, file_type, stored_path)."""
    name = Path(upload.filename or "").name
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_TYPES:
        raise AppError(
            415,
            "UNSUPPORTED_FILE_TYPE",
            "Only .zip (containing a shapefile) and .kml files are supported",
        )

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{uuid.uuid4()}{ext}"
    max_bytes = settings.max_upload_mb * 1024 * 1024

    size = 0
    try:
        with dest.open("wb") as out:
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise AppError(
                        413,
                        "FILE_TOO_LARGE",
                        f"File exceeds the {settings.max_upload_mb} MB limit",
                    )
                out.write(chunk)
        if size == 0:
            raise AppError(400, "EMPTY_FILE", "Uploaded file is empty")
        if ext == ".zip" and not zipfile.is_zipfile(dest):
            raise AppError(400, "INVALID_ZIP", "File is not a valid zip archive")
    except Exception:
        dest.unlink(missing_ok=True)
        raise

    return name, ALLOWED_TYPES[ext], dest
