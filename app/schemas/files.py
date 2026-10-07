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


class FeatureOut(BaseModel):
    index: int
    layer: str | None = None
    geometry_type: str | None = None
    geometry: dict | None = None
    crs: str
    properties: dict
    measurement: dict | None = None


class MeasurementsOut(BaseModel):
    id: str
    crs: str | None = None
    feature_count: int
    features: list[FeatureOut]
