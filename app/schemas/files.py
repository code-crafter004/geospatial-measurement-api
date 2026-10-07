from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    feature_count: int | None = None
    crs: str | None = None
    status: str
    error: str | None = None
    created_at: datetime
