from typing import List, Dict, Optional, Tuple
from pydantic import BaseModel
import datetime

class StandardizedModelResult(BaseModel):
    simulation_id: str
    scenario_id: str
    solver_name: str
    solver_version: str
    crs: str
    
    # Raster output paths
    max_depth_tif: str
    max_velocity_tif: str
    arrival_time_tif: str
    
    # Vector output path
    flood_extent_geojson: str
    
    # Simulation stats
    total_timesteps_executed: int
    computational_time_seconds: float
    flooded_area_sq_meters: float
    max_simulated_depth_m: float
    max_simulated_velocity_mps: float
    
    # Metadata
    generated_at: str
    provenance: str
    limitations: List[str]
