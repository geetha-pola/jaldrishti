from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime

class DamBase(BaseModel):
    name: str
    river: Optional[str] = None
    state: Optional[str] = None
    height_m: Optional[float] = None
    capacity_mcm: Optional[float] = None
    latest_storage_mcm: Optional[float] = None
    last_updated: Optional[datetime] = None

class DamCreate(DamBase):
    lat: float
    lon: float

class DamResponse(DamBase):
    id: int
    created_at: datetime
    # We will return geojson point for the frontend
    geojson: Any

    class Config:
        from_attributes = True
