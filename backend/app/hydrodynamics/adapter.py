import os
import time
import json
import uuid
from datetime import datetime
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.enums import Resampling
from rasterio import features
import geopandas as gpd
from typing import Tuple, Dict, Any, Optional
from abc import ABC, abstractmethod

from numba import njit

from app.scenarios.models import StandardizedModelInput, StandardizedModelResult


class HydrodynamicModelAdapter(ABC):
    """
    Abstract base class for all hydrodynamic model adapters.
    """
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        pass
        
    @property
    @abstractmethod
    def model_version(self) -> str:
        pass
        
    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the model runtime can be executed in the current environment."""
        pass
        
    @abstractmethod
    def prepare_input(self, scenario: StandardizedModelInput, output_dir: str) -> None:
        """Translates the StandardizedModelInput into the specific model's input format."""
        pass
        
    @abstractmethod
    def run(self, scenario: StandardizedModelInput, output_dir: str) -> StandardizedModelResult:
        """Executes the model simulation and returns a StandardizedModelResult.
        Raises an exception if the model is not available.
        """
        pass

# ---------------------------------------------------------
# 1. BASELINE DIFFUSIVE WAVE ADAPTER
# ---------------------------------------------------------

@njit(fastmath=True)
def solve_2d_diffusive_wave(
    elevation: np.ndarray,
    initial_depth: np.ndarray,
    t_hydro: np.ndarray,
    q_hydro: np.ndarray,
    inflow_idx_x: int,
    inflow_idx_y: int,
    dx: float,
    manning_n: float,
    total_sim_time: float
):
    rows, cols = elevation.shape
    depth = initial_depth.copy()
    
    max_depth = np.zeros_like(depth)
    max_velocity = np.zeros_like(depth)
    arrival_time = np.full_like(depth, -1.0)
    
    t = 0.0
    dt = 0.5 
    step = 0
    
    g = 9.81
    
    inflow_vol_total = 0.0
    
    qx = np.zeros((rows, cols + 1))
    qy = np.zeros((rows + 1, cols))
    
    while t < total_sim_time:
        q_inflow = np.interp(t, t_hydro, q_hydro)
        inflow_vol_total += q_inflow * dt
        
        water_surface = elevation + depth
        
        for i in range(rows):
            for j in range(cols - 1):
                hL = depth[i, j]
                hR = depth[i, j+1]
                if hL > 1e-4 or hR > 1e-4:
                    wsL = water_surface[i, j]
                    wsR = water_surface[i, j+1]
                    slope = (wsL - wsR) / dx
                    h_edge = max(wsL, wsR) - max(elevation[i, j], elevation[i, j+1])
                    if h_edge > 1e-4:
                        Sf = np.sign(slope) * np.sqrt(abs(slope))
                        v = (1.0 / manning_n) * (h_edge ** (2.0/3.0)) * Sf
                        v = max(min(v, 30.0), -30.0)
                        qx[i, j+1] = v * h_edge
                    else:
                        qx[i, j+1] = 0.0
                        
        for i in range(rows - 1):
            for j in range(cols):
                hT = depth[i, j]
                hB = depth[i+1, j]
                if hT > 1e-4 or hB > 1e-4:
                    wsT = water_surface[i, j]
                    wsB = water_surface[i+1, j]
                    slope = (wsT - wsB) / dx
                    h_edge = max(wsT, wsB) - max(elevation[i, j], elevation[i+1, j])
                    if h_edge > 1e-4:
                        Sf = np.sign(slope) * np.sqrt(abs(slope))
                        v = (1.0 / manning_n) * (h_edge ** (2.0/3.0)) * Sf
                        v = max(min(v, 30.0), -30.0)
                        qy[i+1, j] = v * h_edge
                    else:
                        qy[i+1, j] = 0.0
                        
        depth[inflow_idx_y, inflow_idx_x] += (q_inflow * dt) / (dx * dx)
        
        for i in range(rows):
            for j in range(cols):
                if depth[i, j] > 1e-4 or (i == inflow_idx_y and j == inflow_idx_x):
                    flux_x = (qx[i, j] - qx[i, j+1]) * dt / dx
                    flux_y = (qy[i, j] - qy[i+1, j]) * dt / dx
                    
                    depth[i, j] += flux_x + flux_y
                    depth[i, j] = max(depth[i, j], 0.0)
                    
                    if depth[i, j] > 0.1 and arrival_time[i, j] < 0:
                        arrival_time[i, j] = t
                        
                    if depth[i, j] > max_depth[i, j]:
                        max_depth[i, j] = depth[i, j]
                        
        for i in range(rows):
            for j in range(cols):
                if depth[i, j] > 1e-4:
                    v_x = max(abs(qx[i, j]), abs(qx[i, j+1])) / depth[i, j]
                    v_y = max(abs(qy[i, j]), abs(qy[i+1, j])) / depth[i, j]
                    v_max_step = np.sqrt(v_x**2 + v_y**2)
                    if v_max_step > max_velocity[i, j]:
                        max_velocity[i, j] = v_max_step
                        
        t += dt
        step += 1
        
    final_vol = 0.0
    for i in range(rows):
        for j in range(cols):
            if depth[i, j] > 0.0:
                final_vol += depth[i, j] * dx * dx
                
    mass_error = inflow_vol_total - final_vol
    
    return max_depth, max_velocity, arrival_time, step, dt, inflow_vol_total, final_vol, mass_error


class BaselineDiffusiveWaveAdapter(HydrodynamicModelAdapter):
    @property
    def model_name(self) -> str:
        return "BASELINE_DIFFUSIVE_WAVE"
        
    @property
    def model_version(self) -> str:
        return "1.0 (Numba Accelerated)"
        
    @property
    def is_available(self) -> bool:
        return True
        
    def prepare_input(self, scenario: StandardizedModelInput, output_dir: str) -> None:
        # For baseline, input preparation happens entirely in memory during run()
        pass

    def run(self, scenario: StandardizedModelInput, output_dir: str) -> StandardizedModelResult:
        os.makedirs(output_dir, exist_ok=True)
        
        bounds = scenario.domain_bounds_utm
        with rasterio.open(scenario.dem_path) as src:
            window = from_bounds(*bounds, transform=src.transform)
            scale_factor = 1.0 / 10.0
            win_transform = src.window_transform(window)
            new_width = int(window.width * scale_factor)
            new_height = int(window.height * scale_factor)
            
            dem_data = src.read(
                1, 
                window=window,
                out_shape=(new_height, new_width),
                resampling=Resampling.bilinear
            )
            
            res_transform = win_transform * win_transform.scale(
                (window.width / new_width),
                (window.height / new_height)
            )
            dx = res_transform[0]
            nodata = src.nodata or 0.0
            
        dem_data = np.where((dem_data == nodata) | np.isnan(dem_data), 9999.0, dem_data)
        manning_n = scenario.manning_roughness.value
        
        t_hydro = np.array([pt.time_seconds for pt in scenario.inflow_hydrograph], dtype=np.float64)
        q_hydro = np.array([pt.discharge_cms for pt in scenario.inflow_hydrograph], dtype=np.float64)
        
        total_sim_time = min(scenario.simulation_duration_hours.value * 3600, 1.0 * 3600)
        
        source_x, source_y = scenario.source_location['lon'], scenario.source_location['lat']
        from pyproj import Transformer
        transformer = Transformer.from_crs("EPSG:4326", scenario.crs, always_xy=True)
        utm_x, utm_y = transformer.transform(source_x, source_y)
        
        col, row = ~res_transform * (utm_x, utm_y)
        inflow_idx_y = min(max(int(row), 0), dem_data.shape[0]-1)
        inflow_idx_x = min(max(int(col), 0), dem_data.shape[1]-1)
        
        initial_depth = np.zeros_like(dem_data)
        
        start_time = time.time()
        max_depth, max_velocity, arrival_time, step, dt, in_vol, out_vol, mass_err = solve_2d_diffusive_wave(
            dem_data, initial_depth, t_hydro, q_hydro, inflow_idx_x, inflow_idx_y,
            dx, manning_n, total_sim_time
        )
        compute_time = time.time() - start_time
        
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
        
        max_depth[max_depth < 0.1] = -9999.0
        max_velocity[max_velocity < 0.01] = -9999.0
        arrival_time[arrival_time < 0] = -9999.0
        
        depth_path = os.path.join(output_dir, f"{sim_id}_max_depth.tif")
        vel_path = os.path.join(output_dir, f"{sim_id}_max_vel.tif")
        arr_path = os.path.join(output_dir, f"{sim_id}_arrival.tif")
        
        with rasterio.open(depth_path, 'w', **out_profile) as dst: dst.write(max_depth.astype('float32'), 1)
        with rasterio.open(vel_path, 'w', **out_profile) as dst: dst.write(max_velocity.astype('float32'), 1)
        with rasterio.open(arr_path, 'w', **out_profile) as dst: dst.write(arrival_time.astype('float32'), 1)
            
        flood_mask = max_depth > 0.0
        shapes = features.shapes(flood_mask.astype('uint8'), transform=res_transform)
        polygons = [shape for shape, val in shapes if val == 1]
        
        extent_path = os.path.join(output_dir, f"{sim_id}_extent.geojson")
        if polygons:
            from shapely.geometry import shape
            geom = [shape(poly) for poly in polygons]
            gdf = gpd.GeoDataFrame(geometry=geom, crs=scenario.crs)
            gdf.to_crs("EPSG:4326").to_file(extent_path, driver="GeoJSON")
            flooded_area = sum([g.area for g in geom])
        else:
            with open(extent_path, 'w') as f: f.write('{"type": "FeatureCollection", "features": []}')
            flooded_area = 0.0
            
        return StandardizedModelResult(
            simulation_id=sim_id,
            scenario_id=scenario.scenario_id,
            solver_name=self.model_name,
            solver_version=self.model_version,
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
            limitations=[
                "BASELINE SOLVER: This uses a simplified 2D Diffusive Wave approximation, not full SWE.",
                "NUMERICAL VELOCITY CAP: The maximum velocity is artificially capped at 30 m/s for numerical stability.",
                "EXTREME HYPOTHETICAL ASSUMPTION: The flood extent represents an engineer-defined stress test, NOT a physically validated real-world event prediction."
            ]
        )

# ---------------------------------------------------------
# 2. SPH ADAPTER
# ---------------------------------------------------------

class SPHAdapter(HydrodynamicModelAdapter):
    @property
    def model_name(self) -> str:
        return "SPH"
        
    @property
    def model_version(self) -> str:
        return "DualSPHysics 5.2 (Integration Ready)"
        
    @property
    def is_available(self) -> bool:
        # SPH binaries (like DualSPHysics/PySPH) are computationally heavy 
        # and require specific OS binaries/CUDA which are not available in this host environment.
        return False
        
    def prepare_input(self, scenario: StandardizedModelInput, output_dir: str) -> None:
        """
        Creates the required XML geometry and particle generation scripts for DualSPHysics.
        In a real environment, this translates the DEM and hydrograph into GenCase XML.
        """
        os.makedirs(output_dir, exist_ok=True)
        xml_path = os.path.join(output_dir, f"{scenario.scenario_id}_sph_case.xml")
        
        # We generate a genuine XML configuration structure for DualSPHysics even though we can't run it.
        xml_content = f"""<?xml version="1.0" encoding="utf-8"?>
<case>
    <casedef>
        <constantsdef>
            <gravity x="0" y="0" z="-9.81" />
            <rhop0 value="1000" />
            <hswl value="0" />
            <gamma value="7" />
            <c0 value="20" />
        </constantsdef>
        <geometry>
            <!-- DEM would be converted to STL boundary particles here -->
            <filemesh file="dem_terrain.stl" />
        </geometry>
        <execution>
            <parameters>
                <parameter key="TimeMax" value="{scenario.simulation_duration_hours.value * 3600}" comment="Time of simulation" />
                <parameter key="IncZ" value="0.5" comment="Initial particle spacing" />
                <parameter key="DtIni" value="0.0001" comment="Initial time step" />
            </parameters>
        </execution>
    </casedef>
</case>
"""
        with open(xml_path, 'w') as f:
            f.write(xml_content)

    def run(self, scenario: StandardizedModelInput, output_dir: str) -> StandardizedModelResult:
        if not self.is_available:
            raise RuntimeError(
                f"Runtime for {self.model_name} is unavailable in the current environment. "
                "Integration boundary is implemented but the DualSPHysics/PySPH executable is missing."
            )
        # In a fully provisioned environment, we would invoke the subprocess here:
        # subprocess.run(["DualSPHysics5.2", "sph_case.xml", "out_dir"])
        # And then parse the generated .vtk/.csv into the StandardizedModelResult.
        pass

# ---------------------------------------------------------
# 3. DELFT3D ADAPTER
# ---------------------------------------------------------

class Delft3DAdapter(HydrodynamicModelAdapter):
    @property
    def model_name(self) -> str:
        return "DELFT3D"
        
    @property
    def model_version(self) -> str:
        return "Delft3D Flexible Mesh (D-Flow FM) 2023.01"
        
    @property
    def is_available(self) -> bool:
        # Delft3D requires the 'dflowfm' executable locally which is not present.
        return False
        
    def prepare_input(self, scenario: StandardizedModelInput, output_dir: str) -> None:
        """
        Translates StandardizedModelInput into D-Flow FM input formats (.mdu, .net, .ext).
        """
        os.makedirs(output_dir, exist_ok=True)
        mdu_path = os.path.join(output_dir, f"{scenario.scenario_id}.mdu")
        
        # MDU (Master Definition Unit) configuration for D-Flow FM
        mdu_content = f"""[geometry]
NetFile = grid.net
BathymetryFile = bathymetry.xyz
WaterLevIni = 0.0

[numerics]
CFLMax = 0.7
MinTimestepBreak = 0.001

[time]
RefDate = 20260901
Tstart = 0
Tstop = {scenario.simulation_duration_hours.value * 3600}

[output]
MapInterval = 300
HisInterval = 300
"""
        with open(mdu_path, 'w') as f:
            f.write(mdu_content)
            
        bnd_path = os.path.join(output_dir, f"{scenario.scenario_id}.bc")
        bnd_content = "[forcing]\nName = dam_breach_inflow\nFunction = timeseries\n"
        for pt in scenario.inflow_hydrograph:
            bnd_content += f"{pt.time_seconds} {pt.discharge_cms}\n"
            
        with open(bnd_path, 'w') as f:
            f.write(bnd_content)

    def run(self, scenario: StandardizedModelInput, output_dir: str) -> StandardizedModelResult:
        if not self.is_available:
            raise RuntimeError(
                f"Runtime for {self.model_name} is unavailable in the current environment. "
                "Integration boundary is implemented but the 'dflowfm' executable is missing."
            )
        pass

# ---------------------------------------------------------
# MODEL REGISTRY
# ---------------------------------------------------------

class ModelRegistry:
    _models = {
        "BASELINE_DIFFUSIVE_WAVE": BaselineDiffusiveWaveAdapter(),
        "SPH": SPHAdapter(),
        "DELFT3D": Delft3DAdapter()
    }
    
    @classmethod
    def get_adapter(cls, model_type: str) -> HydrodynamicModelAdapter:
        if model_type not in cls._models:
            raise ValueError(f"Unknown model type: {model_type}")
        return cls._models[model_type]
        
    @classmethod
    def list_models(cls) -> list:
        return [
            {
                "id": key,
                "name": adapter.model_name,
                "version": adapter.model_version,
                "is_available": adapter.is_available
            }
            for key, adapter in cls._models.items()
        ]
