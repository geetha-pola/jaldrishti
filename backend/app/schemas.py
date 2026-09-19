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
    id: str
    created_at: datetime
    # We will return geojson point for the frontend
    geojson: Any

    class Config:
        from_attributes = True

class SimulationRequest(BaseModel):
    hazard_type: str
    dam_id: Optional[str] = None
    lake_id: Optional[str] = None
    scenario_id: Optional[str] = None
    event_date: Optional[str] = None
    model_type: Optional[str] = "DELFT3D"

class SimulationResponse(BaseModel):
    simulation_id: str
    status: str

class SimulationStatusResponse(BaseModel):
    simulation_id: str
    status: str
    current_stage: Optional[str] = None
    progress: Optional[float] = None
    error: Optional[str] = None
    requested_model: Optional[str] = None
    actual_model: Optional[str] = None
    config: Optional[dict] = None
    results: Optional[dict] = None

class SimulationResultsResponse(BaseModel):
    simulation_id: str
    status: str
    extent_path: Optional[str] = None
    depth_path: Optional[str] = None
    arrival_path: Optional[str] = None
    impact_summary_path: Optional[str] = None
    satellite_validation_path: Optional[str] = None
    max_depth_m: Optional[float] = None
    max_velocity_mps: Optional[float] = None

class GlacialLakeBase(BaseModel):
    name: str
    latitude: float
    longitude: float
    elevation_m: Optional[float] = None
    area_sq_m: Optional[float] = None
    estimated_depth_m: Optional[float] = None
    estimated_volume_m3: Optional[float] = None
    downstream_river: Optional[str] = None
    source: Optional[str] = None
    source_date: Optional[str] = None
    provenance: str
    notes: Optional[str] = None

class GlacialLakeResponse(GlacialLakeBase):
    id: str
    geojson: Any
