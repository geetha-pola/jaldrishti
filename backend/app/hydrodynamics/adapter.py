import os
import time
import json
import uuid
import numpy as np
import rasterio
from rasterio import features
from rasterio.warp import reproject, Resampling
from rasterio.windows import from_bounds
import geopandas as gpd
from numba import njit
from datetime import datetime

from app.scenarios.models import StandardizedModelInput
from app.hydrodynamics.models import StandardizedModelResult

@njit(parallel=False)
def solve_2d_diffusive_wave(
    dem, initial_depth, t_hydro, q_hydro, inflow_idx_x, inflow_idx_y, 
    dx, manning_n, total_sim_time
):
    """
    Numba-accelerated 2D Diffusive Wave Solver with 4-way routing and stability controls.
    """
    rows, cols = dem.shape
    depth = initial_depth.copy()
    
    max_depth = np.zeros_like(depth)
    max_velocity = np.zeros_like(depth)
    arrival_time = np.full(depth.shape, -1.0)
    
    g = 9.81
    t = 0.0
    step = 0
    inflow_vol_total = 0.0
    
    # Adaptive timestep parameters
    # The Courant-Friedrichs-Lewy (CFL) condition requires: dt <= dx / (v + sqrt(gh))
    # We will start with a conservative dt and adapt if necessary, but for simplicity
    # in this baseline, we'll fix a small dt of 0.5 seconds which is stable for dx=90m up to v=150m/s
    dt = 0.5 
    
    # Allocate flux arrays
    flux_x = np.zeros_like(depth)
    flux_y = np.zeros_like(depth)
    
    while t < total_sim_time:
        # Interpolate inflow
        q_in = 0.0
        if t <= t_hydro[-1]:
            for k in range(1, len(t_hydro)):
                if t <= t_hydro[k]:
                    dt_hydro = t_hydro[k] - t_hydro[k-1]
                    weight = (t - t_hydro[k-1]) / dt_hydro
                    q_in = q_hydro[k-1] + weight * (q_hydro[k] - q_hydro[k-1])
                    break
                    
        dh_in = (q_in * dt) / (dx * dx)
        depth[inflow_idx_y, inflow_idx_x] += dh_in
        inflow_vol_total += q_in * dt
        
        water_elevation = dem + depth
        new_depth = depth.copy()
        
        # Arrays to accumulate received volume to avoid race conditions in parallel
        # or simplify logic. Since this is explicit sequential, we can just use new_depth.
        # But to be clean, let's track dvol
        dvol = np.zeros_like(depth)
        
        v_max_step = np.zeros_like(depth)
        
        # Compute outward fluxes for every cell
        for i in range(1, rows - 1):
            for j in range(1, cols - 1):
                h0 = depth[i, j]
                if h0 < 0.01:
                    continue
                    
                w0 = water_elevation[i, j]
                z0 = dem[i, j]
                
                
                # Unrolled neighbors: East, West, South, North for Numba speed
                q_out = np.zeros(4)
                
                # 0: East
                ni, nj = i, j+1
                wn = water_elevation[ni, nj]
                zn = dem[ni, nj]
                if w0 > wn + 0.001:
                    h_flow = max(w0 - max(z0, zn), 0.0)
                    if h_flow > 0.01:
                        Sf = (w0 - wn) / dx
                        v_out = (1.0 / manning_n) * (h_flow**(2.0/3.0)) * np.sqrt(Sf)
                        v_out = min(v_out, 30.0)
                        q_out[0] = v_out * h_flow * dx
                        v_max_step[i, j] = max(v_max_step[i, j], v_out)
                        
                # 1: West
                ni, nj = i, j-1
                wn = water_elevation[ni, nj]
                zn = dem[ni, nj]
                if w0 > wn + 0.001:
                    h_flow = max(w0 - max(z0, zn), 0.0)
                    if h_flow > 0.01:
                        Sf = (w0 - wn) / dx
                        v_out = (1.0 / manning_n) * (h_flow**(2.0/3.0)) * np.sqrt(Sf)
                        v_out = min(v_out, 30.0)
                        q_out[1] = v_out * h_flow * dx
                        v_max_step[i, j] = max(v_max_step[i, j], v_out)
                        
                # 2: South
                ni, nj = i+1, j
                wn = water_elevation[ni, nj]
                zn = dem[ni, nj]
                if w0 > wn + 0.001:
                    h_flow = max(w0 - max(z0, zn), 0.0)
                    if h_flow > 0.01:
                        Sf = (w0 - wn) / dx
                        v_out = (1.0 / manning_n) * (h_flow**(2.0/3.0)) * np.sqrt(Sf)
                        v_out = min(v_out, 30.0)
                        q_out[2] = v_out * h_flow * dx
                        v_max_step[i, j] = max(v_max_step[i, j], v_out)
                        
                # 3: North
                ni, nj = i-1, j
                wn = water_elevation[ni, nj]
                zn = dem[ni, nj]
                if w0 > wn + 0.001:
                    h_flow = max(w0 - max(z0, zn), 0.0)
                    if h_flow > 0.01:
                        Sf = (w0 - wn) / dx
                        v_out = (1.0 / manning_n) * (h_flow**(2.0/3.0)) * np.sqrt(Sf)
                        v_out = min(v_out, 30.0)
                        q_out[3] = v_out * h_flow * dx
                        v_max_step[i, j] = max(v_max_step[i, j], v_out)
                
                # Total volume trying to leave
                sum_q = q_out[0] + q_out[1] + q_out[2] + q_out[3]
                vol_out = sum_q * dt
                avail_vol = h0 * dx * dx
                
                # Mass conservation scaling
                scale = 1.0
                if vol_out > avail_vol:
                    scale = avail_vol / vol_out
                    
                # Apply scaled fluxes
                if q_out[0] > 0:
                    av = q_out[0] * dt * scale
                    dvol[i, j] -= av
                    dvol[i, j+1] += av
                if q_out[1] > 0:
                    av = q_out[1] * dt * scale
                    dvol[i, j] -= av
                    dvol[i, j-1] += av
                if q_out[2] > 0:
                    av = q_out[2] * dt * scale
                    dvol[i, j] -= av
                    dvol[i+1, j] += av
                if q_out[3] > 0:
                    av = q_out[3] * dt * scale
                    dvol[i, j] -= av
                    dvol[i-1, j] += av
                        
        # Apply dvol
        for i in range(rows):
            for j in range(cols):
                new_depth[i, j] += dvol[i, j] / (dx * dx)
                
        depth = new_depth
        
        # Track maximums
        for i in range(rows):
            for j in range(cols):
                if depth[i, j] > 0.1 and arrival_time[i, j] == -1.0:
                    arrival_time[i, j] = t
                if depth[i, j] > max_depth[i, j]:
                    max_depth[i, j] = depth[i, j]
                
                if v_max_step[i, j] > max_velocity[i, j]:
                    max_velocity[i, j] = v_max_step[i, j]
                    
        t += dt
        step += 1
        
    # Calculate final mass balance
    # Total volume in grid = sum(depth * dx * dx)
    final_vol = 0.0
    for i in range(rows):
        for j in range(cols):
            if depth[i, j] > 0.0:
                final_vol += depth[i, j] * dx * dx
                
    mass_error = inflow_vol_total - final_vol
    
    return max_depth, max_velocity, arrival_time, step, dt, inflow_vol_total, final_vol, mass_error

class BaselineHydrodynamicAdapter:
    def __init__(self, output_dir: str = "data/hydro_results"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        
    def execute_simulation(self, scenario_json_path: str) -> StandardizedModelResult:
        with open(scenario_json_path, 'r') as f:
            data = json.load(f)
            
        scenario = StandardizedModelInput(**data)
        
        # 1. Prepare Computational Grid
        # We crop the DEM to the domain bounds to save memory and time
        bounds = scenario.domain_bounds_utm
        
        with rasterio.open(scenario.dem_path) as src:
            # Crop window
            window = from_bounds(*bounds, transform=src.transform)
            # Read and coarsen by factor of 10 (~300m) for baseline solver speed
            scale_factor = 1.0 / 10.0
            
            # Ensure window is valid
            win_transform = src.window_transform(window)
            
            # Read resampled data
            new_width = int(window.width * scale_factor)
            new_height = int(window.height * scale_factor)
            
            dem_data = src.read(
                1, 
                window=window,
                out_shape=(new_height, new_width),
                resampling=Resampling.bilinear
            )
            
            # Update transform for coarsened grid
            res_transform = win_transform * win_transform.scale(
                (window.width / new_width),
                (window.height / new_height)
            )
            dx = res_transform[0] # Pixel width in meters
            nodata = src.nodata or 0.0
            
        # Treat nodata as high elevation walls so water doesn't flow off arbitrarily
        dem_data = np.where((dem_data == nodata) | np.isnan(dem_data), 9999.0, dem_data)
        
        # 2. Setup Boundary Conditions (Hydrograph)
        manning_n = scenario.manning_roughness.value
        
        # Pass hydrograph points directly to numba to interpolate dynamically
        t_hydro = np.array([pt.time_seconds for pt in scenario.inflow_hydrograph], dtype=np.float64)
        q_hydro = np.array([pt.discharge_cms for pt in scenario.inflow_hydrograph], dtype=np.float64)
        
        total_sim_time = min(scenario.simulation_duration_hours.value * 3600, 1.0 * 3600)
        
        # Find dam pixel index in cropped grid
        source_x, source_y = scenario.source_location['lon'], scenario.source_location['lat']
        # Reproject source to UTM to find pixel
        from pyproj import Transformer
        transformer = Transformer.from_crs("EPSG:4326", scenario.crs, always_xy=True)
        utm_x, utm_y = transformer.transform(source_x, source_y)
        
        # Convert UTM to pixel index
        # Inverse transform maps (x, y) -> (col, row)
        col, row = ~res_transform * (utm_x, utm_y)
        inflow_idx_y = min(max(int(row), 0), dem_data.shape[0]-1)
        inflow_idx_x = min(max(int(col), 0), dem_data.shape[1]-1)
        
        initial_depth = np.zeros_like(dem_data)
        
        # 3. Execute Numba Solver
        print(f"Starting 2D Baseline Solver on {dem_data.shape} grid for {total_sim_time} seconds")
        start_time = time.time()
        max_depth, max_velocity, arrival_time, step, dt, in_vol, out_vol, mass_err = solve_2d_diffusive_wave(
            dem_data, initial_depth, t_hydro, q_hydro, inflow_idx_x, inflow_idx_y,
            dx, manning_n, total_sim_time
        )
        compute_time = time.time() - start_time
        print(f"Solver finished in {compute_time:.2f} seconds. Steps: {step}, Final dt: {dt}")
        print(f"Mass balance error: {mass_err:.2f} m3 (Inflow: {in_vol:.2f}, Grid: {out_vol:.2f})")
        
        # 4. Process Results (Rasters and Polygons)
        sim_id = f"SIM-{uuid.uuid4().hex[:6]}"
        
        out_profile = {
            'driver': 'GTiff',
            'height': dem_data.shape[0],
            'width': dem_data.shape[1],
            'count': 1,
            'dtype': 'float32',
            'crs': scenario.crs,
            'transform': res_transform,
            'nodata': -9999.0
        }
        
        # Mask out dry cells
        max_depth[max_depth < 0.1] = -9999.0
        max_velocity[max_velocity < 0.01] = -9999.0
        arrival_time[arrival_time < 0] = -9999.0
        
        depth_path = os.path.join(self.output_dir, f"{sim_id}_max_depth.tif")
        vel_path = os.path.join(self.output_dir, f"{sim_id}_max_vel.tif")
        arr_path = os.path.join(self.output_dir, f"{sim_id}_arrival.tif")
        
        with rasterio.open(depth_path, 'w', **out_profile) as dst: dst.write(max_depth.astype('float32'), 1)
        with rasterio.open(vel_path, 'w', **out_profile) as dst: dst.write(max_velocity.astype('float32'), 1)
        with rasterio.open(arr_path, 'w', **out_profile) as dst: dst.write(arrival_time.astype('float32'), 1)
            
        # Extract flood extent polygon
        # Create a mask for flooded areas (depth > 0.1m)
        flood_mask = max_depth > 0.0
        shapes = features.shapes(flood_mask.astype('uint8'), transform=res_transform)
        polygons = [shape for shape, val in shapes if val == 1]
        
        extent_path = os.path.join(self.output_dir, f"{sim_id}_extent.geojson")
        if polygons:
            from shapely.geometry import shape
            geom = [shape(poly) for poly in polygons]
            gdf = gpd.GeoDataFrame(geometry=geom, crs=scenario.crs)
            # Reproject to 4326 for standard geojson
            gdf.to_crs("EPSG:4326").to_file(extent_path, driver="GeoJSON")
            flooded_area = sum([g.area for g in geom])
        else:
            with open(extent_path, 'w') as f: f.write('{"type": "FeatureCollection", "features": []}')
            flooded_area = 0.0
            
        limitations = [
            "BASELINE SOLVER: This uses a simplified 2D Diffusive Wave approximation, not full SWE.",
            "SPH/Delft3D ABSTRACTION: This baseline executes behind the Model Adapter as SPH/Delft3D binaries are unsupported in this environment.",
            "COARSE GRID: The DEM was resampled to ~300m to allow fast execution.",
            "EXTREME HYPOTHETICAL ASSUMPTION: The flood extent represents an engineer-defined stress test, NOT a physically validated real-world event prediction."
        ]
        
        return StandardizedModelResult(
            simulation_id=sim_id,
            scenario_id=scenario.scenario_id,
            solver_name="Baseline 2D Diffusive Wave (Numba Accelerated)",
            solver_version="1.0",
            crs=scenario.crs,
            max_depth_tif=depth_path,
            max_velocity_tif=vel_path,
            arrival_time_tif=arr_path,
            flood_extent_geojson=extent_path,
            total_timesteps_executed=step,
            computational_time_seconds=compute_time,
            flooded_area_sq_meters=flooded_area,
            max_simulated_depth_m=float(np.max(max_depth)),
            max_simulated_velocity_mps=float(np.max(max_velocity)),
            generated_at=datetime.utcnow().isoformat(),
            provenance="Baseline Hydrodynamic Adapter Executed Locally",
            limitations=limitations
        )
