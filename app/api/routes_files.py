from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import UploadedFile
from app.db.session import get_db
from app.schemas.files import FileOut
from app.services.ingestion import save_upload

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/", response_model=FileOut, status_code=201)
def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    name, file_type, path = save_upload(file)
    record = UploadedFile(filename=name, file_type=file_type, stored_path=str(path))
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/{file_id}/", response_model=FileOut)
def get_file(file_id: str, db: Session = Depends(get_db)):
    record = db.get(UploadedFile, file_id)
    if record is None:
        raise AppError(404, "FILE_NOT_FOUND", f"No file with id {file_id}")
    return record
