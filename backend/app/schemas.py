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

class SimulationRequest(BaseModel):
    hazard_type: str
    dam_id: str
    scenario_id: Optional[str] = None
    event_date: Optional[str] = None

class SimulationResponse(BaseModel):
    simulation_id: str
    status: str

class SimulationStatusResponse(BaseModel):
    simulation_id: str
    status: str
    current_stage: Optional[str] = None
    progress: Optional[float] = None
    error: Optional[str] = None

class SimulationResultsResponse(BaseModel):
    simulation_id: str
    status: str
    extent_path: Optional[str] = None
    depth_path: Optional[str] = None
    arrival_path: Optional[str] = None
    impact_summary_path: Optional[str] = None
    satellite_validation_path: Optional[str] = None
