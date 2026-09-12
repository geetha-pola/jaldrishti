from enum import Enum
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field, field_validator

class ProvenanceStatus(str, Enum):
    OBSERVED = "OBSERVED"
    PUBLISHED = "PUBLISHED"
    ESTIMATED = "ESTIMATED"
    ENGINEER_DEFINED = "ENGINEER_DEFINED"
    ASSUMED = "ASSUMED"

class ScenarioType(str, Enum):
    HYPOTHETICAL = "HYPOTHETICAL_DAM_BREAK"
    RECONSTRUCTED = "RECONSTRUCTED_OBSERVED_EVENT"

class ParameterValue(BaseModel):
    value: float
    unit: str
    provenance: ProvenanceStatus
    reference: Optional[str] = None
    assumptions: Optional[str] = None

class DamBreakParameters(BaseModel):
    dam_height: ParameterValue
    initial_water_level: ParameterValue
    initial_storage_volume: ParameterValue  # typically cubic meters
    breach_width: ParameterValue
    breach_depth: ParameterValue
    breach_formation_time: ParameterValue
    
    @field_validator('*')
    def check_non_negative(cls, v):
        if v.value < 0:
            raise ValueError(f"Physical parameter cannot be negative. Got {v.value}")
        return v

class HydrographPoint(BaseModel):
    time_seconds: float
    discharge_cms: float # cubic meters per second

class StandardizedModelInput(BaseModel):
    """
    Common data structure to be consumed by any future solver (SPH, Delft3D, etc).
    Contains no solver-specific logic.
    """
    scenario_id: str
    scenario_name: str
    hazard_type: str
    scenario_type: ScenarioType
    source_location: Dict[str, float]  # {'lat': x, 'lon': y}
    dem_path: str
    crs: str
    simulation_domain_geojson: str
    domain_bounds_utm: Tuple[float, float, float, float]
    
    # Physics parameters
    breach_parameters: DamBreakParameters
    inflow_hydrograph: List[HydrographPoint]
    
    # Simulation configs
    simulation_duration_hours: ParameterValue
    timestep_seconds: ParameterValue
    manning_roughness: ParameterValue
    
    # Metatdata
    generated_at: str
    limitations: List[str]
