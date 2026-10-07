from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Feature, FileStatus, UploadedFile
from app.db.session import get_db
from app.schemas.files import FeatureOut, FileOut, MeasurementsOut
from app.services.ingestion import save_upload
from app.services.processing import process_file

router = APIRouter(prefix="/api/files", tags=["files"])


def _get_file_or_404(db: Session, file_id: str) -> UploadedFile:
    record = db.get(UploadedFile, file_id)
    if record is None:
        raise AppError(404, "FILE_NOT_FOUND", f"No file with id {file_id}")
    return record


@router.post("/", response_model=FileOut, status_code=201)
def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    name, file_type, path = save_upload(file)
    record = UploadedFile(filename=name, file_type=file_type, stored_path=str(path))
    db.add(record)
    db.commit()
    db.refresh(record)
    return process_file(db, record)


@router.get("/{file_id}/", response_model=FileOut)
def get_file(file_id: str, db: Session = Depends(get_db)):
    return _get_file_or_404(db, file_id)


@router.get("/{file_id}/measurements/", response_model=MeasurementsOut)
def get_measurements(file_id: str, db: Session = Depends(get_db)):
    record = _get_file_or_404(db, file_id)
    if record.status != FileStatus.COMPLETED.value:
        raise AppError(
            409,
            "FILE_NOT_READY",
            f"File status is {record.status}; measurements are not available",
        )

    rows = db.scalars(
        select(Feature)
        .where(Feature.file_id == file_id)
        .order_by(Feature.feature_index)
    ).all()

    return MeasurementsOut(
        id=record.id,
        crs=record.crs,
        feature_count=len(rows),
        features=[
            FeatureOut(
                index=r.feature_index,
                layer=r.layer,
                geometry_type=r.geometry_type,
                geometry=r.geometry,
                crs=r.crs,
                properties=r.properties,
                measurement=None,  # filled in v0.4.0
            )
            for r in rows
        ],
    )
