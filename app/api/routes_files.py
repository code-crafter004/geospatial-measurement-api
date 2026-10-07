from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Feature, FileStatus, UploadedFile
from app.db.session import get_db
from app.schemas.files import FeatureOut, FileOut, MeasurementsOut
from app.services.ingestion import save_upload
from app.services.processing import process_file

router = APIRouter(prefix="/api/files", tags=["files"])

DbSession = Annotated[Session, Depends(get_db)]


def _get_file_or_404(db: Session, file_id: str) -> UploadedFile:
    record = db.get(UploadedFile, file_id)
    if record is None:
        raise AppError(404, "FILE_NOT_FOUND", f"No file with id {file_id}")
    return record


@router.post("/", response_model=FileOut, status_code=201)
def upload_file(db: DbSession, file: UploadFile = File(...)):
    name, file_type, path = save_upload(file)
    record = UploadedFile(filename=name, file_type=file_type, stored_path=str(path))
    db.add(record)
    db.commit()
    db.refresh(record)
    return process_file(db, record)


@router.get("/", response_model=list[FileOut])
def list_files(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    stmt = select(UploadedFile).order_by(UploadedFile.created_at.desc())
    return db.scalars(stmt.offset(offset).limit(limit)).all()


@router.get("/{file_id}/", response_model=FileOut)
def get_file(file_id: str, db: DbSession):
    return _get_file_or_404(db, file_id)


@router.get("/{file_id}/measurements/", response_model=MeasurementsOut)
def get_measurements(
    file_id: str,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    geometry_type: Annotated[str | None, Query()] = None,
):
    record = _get_file_or_404(db, file_id)
    if record.status != FileStatus.COMPLETED.value:
        raise AppError(
            409,
            "FILE_NOT_READY",
            f"File status is {record.status}; measurements are not available",
        )

    stmt = select(Feature).where(Feature.file_id == file_id)
    if geometry_type:
        stmt = stmt.where(Feature.geometry_type == geometry_type)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Feature.feature_index).offset(offset).limit(limit)
    ).all()

    return MeasurementsOut(
        id=record.id,
        crs=record.crs,
        feature_count=total,
        limit=limit,
        offset=offset,
        features=[
            FeatureOut(
                index=r.feature_index,
                layer=r.layer,
                geometry_type=r.geometry_type,
                geometry=r.geometry,
                crs=r.crs,
                properties=r.properties,
                measurement=r.measurement,
            )
            for r in rows
        ],
    )
