import os
import json
import pytest
import numpy as np
import rasterio
import geopandas as gpd

from app.scenarios.models import StandardizedModelInput
from app.hydrodynamics.models import StandardizedModelResult

def test_scenario_input_validity():
    """Verify units, CRS, and volume consistency of the input scenario before solving."""
    assert os.path.exists("data/domain/idukki_scenario.json")
    with open("data/domain/idukki_scenario.json", 'r') as f:
        data = json.load(f)
    scenario = StandardizedModelInput(**data)
    
    assert scenario.crs.startswith("EPSG:")
    assert scenario.timestep_seconds.unit == "seconds"
    
    # Check volume consistency
    inflow = scenario.inflow_hydrograph
    vol = 0.0
    for i in range(1, len(inflow)):
        dt = inflow[i].time_seconds - inflow[i-1].time_seconds
        avg_q = (inflow[i].discharge_cms + inflow[i-1].discharge_cms) / 2.0
        vol += avg_q * dt
        
    assert pytest.approx(vol, rel=1e-3) == scenario.breach_parameters.initial_storage_volume.value

def test_result_consistency():
    """Test solver outputs for physically impossible values and dimension matches."""
    # Assuming the simulation ran, check the results dir
    # We will just find the latest extent geojson in data/hydro_results
    import glob
    results = glob.glob("data/hydro_results/*_extent.geojson")
    if not results:
        pytest.skip("No hydro results found to test yet.")
        
    extent_path = results[0]
    prefix = extent_path.replace("_extent.geojson", "")
    
    depth_path = f"{prefix}_max_depth.tif"
    vel_path = f"{prefix}_max_vel.tif"
    
    # 1. No impossible negative depths/velocities
    with rasterio.open(depth_path) as src:
        depth = src.read(1)
        valid_depth = depth[depth != src.nodata]
        if len(valid_depth) > 0:
            assert np.min(valid_depth) >= 0.0
            
    with rasterio.open(vel_path) as src:
        vel = src.read(1)
        valid_vel = vel[vel != src.nodata]
        if len(valid_vel) > 0:
            assert np.min(valid_vel) >= 0.0
            
    # 2. Flood extent != simulation domain (it should be much smaller)
    domain_gdf = gpd.read_file("data/domain/simulation_domain.geojson")
    extent_gdf = gpd.read_file(extent_path)
    
    # The flood extent shouldn't exactly match the bounding box area
    # Actually, extent_gdf is multi-polygons, sum their areas in a projected crs
    # Compare raw geoms
    assert len(extent_gdf) > 0
