import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Feature, FileStatus, UploadedFile
from app.services.parsing import ParseError, parse_file

logger = logging.getLogger(__name__)


def process_file(db: Session, record: UploadedFile) -> UploadedFile:
    record.status = FileStatus.PROCESSING.value
    db.commit()

    try:
        parsed = parse_file(Path(record.stored_path), record.file_type)
    except ParseError as exc:
        record.status = FileStatus.FAILED.value
        record.error = str(exc)
    except Exception:
        logger.exception("Unexpected error while processing file %s", record.id)
        record.status = FileStatus.FAILED.value
        record.error = "Unexpected error while reading the file"
    else:
        db.add_all(
            Feature(
                file_id=record.id,
                feature_index=f.index,
                layer=f.layer,
                geometry_type=f.geometry_type,
                geometry=f.geometry,
                crs=parsed.crs,
                properties=f.properties,
            )
            for f in parsed.features
        )
        record.crs = parsed.crs
        record.feature_count = len(parsed.features)
        record.status = FileStatus.COMPLETED.value
        record.error = None

    db.commit()
    db.refresh(record)
    return record
