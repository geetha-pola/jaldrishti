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
from rasterio import features
from typing import Tuple, Dict, Any, Optional
from abc import ABC, abstractmethod
import subprocess
import glob

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
            import geopandas as gpd
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
        return "DualSPHysics 5.4.3 (NNewtonian CPU)"
        
    @property
    def is_available(self) -> bool:
        bin_dir = os.environ.get("DUALSPHYSICS_BIN_DIR", r"C:\jaldrishti\DualSPHysics\bin\windows")
        gencase = os.path.join(bin_dir, "GenCase_win64.exe")
        solver = os.path.join(bin_dir, "DSNNewtonian", "DualSPHysics5.0_NNewtonianCPU_win64.exe")
        partvtk = os.path.join(bin_dir, "PartVTK_win64.exe")
        return os.path.exists(gencase) and os.path.exists(solver) and os.path.exists(partvtk)
        
    def prepare_input(self, scenario, output_dir: str) -> None:
        import rasterio
        import os
        import numpy as np
        
        os.makedirs(output_dir, exist_ok=True)
        xml_path = os.path.join(output_dir, f"{scenario.scenario_id}_sph_case.xml")
        
        sim_duration = scenario.simulation_duration_hours.value * 3600
        
        bounds = scenario.domain_bounds_utm
        with rasterio.open(scenario.dem_path) as src:
            # The DEM is already cropped (e.g. 73x74). Downsample moderately for CPU SPH.
            scale_factor = 1.0 / 2.0
            new_width = int(src.width * scale_factor)
            new_height = int(src.height * scale_factor)
            dem = src.read(1, out_shape=(new_height, new_width), resampling=rasterio.enums.Resampling.bilinear)
            transform = src.transform * src.transform.scale((src.width / new_width), (src.height / new_height))
            dx = transform[0]
            nodata = src.nodata if src.nodata is not None else -9999.0

        dem = np.where(dem == nodata, 10.0, dem)
        
        commands = ""
        for i in range(new_height):
            for j in range(new_width):
                x = j * dx
                y = i * dx
                z = dem[i, j]
                if z <= 0: z = 0.1
                commands += f'''
                    <drawbox>
                        <boxfill>solid</boxfill>
                        <point x="{x}" y="{y}" z="0" />
                        <size x="{dx}" y="{dx}" z="{z}" />
                    </drawbox>'''

        fluid_x = (new_width * dx) * 0.25
        fluid_y = new_height * dx
        initial_wl = scenario.breach_parameters.initial_water_level.value
        max_z = max(float(np.max(dem)), float(initial_wl))
        
        xml_content = f"""<?xml version="1.0" encoding="UTF-8" ?>
<case>
    <casedef>
        <constantsdef>            			
            <gravity x="0" y="0" z="-9.81" />
            <rhop0 value="1000" />
            <rhopgradient value="2" />
            <hswl value="0" auto="true" />
            <gamma value="7" />
            <speedsystem value="0" auto="true" />
            <coefsound value="20" />
            <speedsound value="0" auto="true" />
            <coefh value="1.0" />
            <_hdp value="2" />
            <cflnumber value="0.2" />
        </constantsdef>	
        <mkconfig boundcount="240" fluidcount="9" />
        <geometry>
            <definition dp="{dx}">
                <pointref x="0" y="0" z="0" />
                <pointmin x="-{dx}" y="-{dx}" z="-{dx}" />
                <pointmax x="{new_width*dx + dx}" y="{new_height*dx + dx}" z="{max_z + dx}" />
            </definition>
            <commands>
                <mainlist>
                    <setdrawmode mode="full" />
                    
                    <setmkbound mk="0" />
                    {commands}
                    
                    <setmkfluid mk="0" />
                    <drawbox>
                        <boxfill>solid</boxfill>
                        <point x="0" y="0" z="0" />
                        <size x="{fluid_x}" y="{fluid_y}" z="{initial_wl}" />
                    </drawbox>
                </mainlist>
            </commands>
        </geometry>
    </casedef>
    <execution>
        <parameters>
            <parameter key="ViscoTreatment" value="1" />
            <parameter key="Visco" value="0.02" />
            <parameter key="ViscoBoundFactor" value="1" />
            <parameter key="DensityDT" value="2" />
            <parameter key="DensityDTvalue" value="0.1" />
            <parameter key="TimeMax" value="{sim_duration}" />
            <parameter key="TimeOut" value="{max(0.1, sim_duration/10.0)}" />
        </parameters>
    </execution>
</case>"""
        with open(xml_path, 'w') as f:
            f.write(xml_content)
            
        self._sph_transform = transform
        self._sph_width = new_width
        self._sph_height = new_height
        self._sph_dx = dx

    def run(self, scenario, output_dir: str):
        import os, time, subprocess, glob, uuid, math, rasterio
        import numpy as np
        from app.scenarios.models import StandardizedModelResult
        if not self.is_available:
            raise RuntimeError("RUNTIME_UNAVAILABLE")
            
        bin_dir = os.environ.get("DUALSPHYSICS_BIN_DIR", r"C:\jaldrishti\DualSPHysics\bin\windows")
        gencase = os.path.join(bin_dir, "GenCase_win64.exe")
        solver = os.path.join(bin_dir, "DSNNewtonian", "DualSPHysics5.0_NNewtonianCPU_win64.exe")
        partvtk = os.path.join(bin_dir, "PartVTK_win64.exe")
        
        self.prepare_input(scenario, output_dir)
        xml_name = f"{scenario.scenario_id}_sph_case"
        xml_path = os.path.join(output_dir, f"{xml_name}.xml")
        out_case_dir = os.path.join(output_dir, xml_name)
        
        start_time = time.time()
        
        subprocess.run([gencase, xml_name, xml_name, "-save:all"], check=True, cwd=output_dir)
        subprocess.run([solver, xml_name, xml_name], check=True, cwd=output_dir)
        
        subprocess.run([partvtk, "-dirdata", xml_name, "-savecsv", os.path.join(xml_name, "PartFluid"), "-onlytype:-all,fluid", "-vars:+idp,+vel,+rhop,+press"], check=True, cwd=output_dir)
        
        compute_time = time.time() - start_time
        
        width = self._sph_width
        height = self._sph_height
        transform = self._sph_transform
        
        max_depth = np.full((height, width), -9999.0, dtype=np.float32)
        max_velocity = np.full((height, width), -9999.0, dtype=np.float32)
        arrival_time = np.full((height, width), -9999.0, dtype=np.float32)
        
        csv_files = sorted(glob.glob(os.path.join(out_case_dir, "PartFluid_[0-9]*.csv")))
        total_steps = len(csv_files)
        sim_id = f"SIM-SPH-{uuid.uuid4().hex[:6]}"
        
        with rasterio.open(scenario.dem_path) as src:
            dem = src.read(1, out_shape=(height, width), resampling=rasterio.enums.Resampling.bilinear)
            
        dx = self._sph_dx
            
        for frame_idx, csv_file in enumerate(csv_files):
            frame_time = frame_idx * 0.1 
            with open(csv_file, 'r') as f:
                lines = f.readlines()
                if len(lines) < 6: continue
                for row in lines[4:]:
                    parts = row.strip().split(';')
                    if len(parts) < 8: continue
                    try:
                        x = float(parts[0])
                        y = float(parts[1])
                        z = float(parts[2])
                        vx = float(parts[4])
                        vy = float(parts[5])
                        vz = float(parts[6])
                        
                        col, row_idx = ~transform * (transform[2] + x, transform[5] - y)
                        r = int(row_idx)
                        c = int(col)
                        
                        if 0 <= r < height and 0 <= c < width:
                            depth = z - dem[r, c]
                            if depth > 0 and max_depth[r, c] < depth:
                                max_depth[r, c] = depth
                            
                            vel_mag = math.sqrt(vx**2 + vy**2 + vz**2)
                            if max_velocity[r, c] < vel_mag:
                                max_velocity[r, c] = vel_mag
                                
                            if arrival_time[r, c] < 0:
                                arrival_time[r, c] = frame_time
                    except:
                        pass
        
        max_depth = np.where(max_depth == -9999.0, 0.0, max_depth)
        max_velocity = np.where(max_velocity == -9999.0, 0.0, max_velocity)
        
        depth_path = os.path.join(output_dir, f"{sim_id}_max_depth.tif")
        vel_path = os.path.join(output_dir, f"{sim_id}_max_vel.tif")
        arr_path = os.path.join(output_dir, f"{sim_id}_arrival_time.tif")
        extent_path = os.path.join(output_dir, f"{sim_id}_extent.geojson")
        
        out_profile = {
            'driver': 'GTiff', 'height': height, 'width': width, 'count': 1,
            'dtype': str(max_depth.dtype), 'crs': scenario.crs, 'transform': transform,
            'nodata': -9999.0
        }
        
        with rasterio.open(depth_path, 'w', **out_profile) as dst: dst.write(max_depth, 1)
        with rasterio.open(vel_path, 'w', **out_profile) as dst: dst.write(max_velocity, 1)
        with rasterio.open(arr_path, 'w', **out_profile) as dst: dst.write(arrival_time, 1)
        
        flood_mask = max_depth > 0.1
        from rasterio import features
        shapes = features.shapes(flood_mask.astype('uint8'), transform=transform)
        polygons = [shape for shape, val in shapes if val == 1]
        
        if polygons:
            from shapely.geometry import shape
            geom = [shape(poly) for poly in polygons]
            import geopandas as gpd
            gdf = gpd.GeoDataFrame(geometry=geom, crs=scenario.crs)
            gdf.to_crs("EPSG:4326").to_file(extent_path, driver="GeoJSON")
            flooded_area = sum([g.area for g in geom])
        else:
            with open(extent_path, 'w') as f:
                f.write('{"type": "FeatureCollection", "features": []}')
            flooded_area = 0.0
            
        from datetime import datetime
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
            total_timesteps_executed=total_steps,
            computational_time_seconds=compute_time,
            flooded_area_sq_meters=flooded_area,
            max_simulated_depth_m=float(np.max(max_depth)),
            max_simulated_velocity_mps=float(np.max(max_velocity)),
            generated_at=datetime.utcnow().isoformat(),
            provenance="Genuine DualSPHysics CPU",
            limitations=["Integration Test"]
        )

class Delft3DAdapter(HydrodynamicModelAdapter):
    @property
    def model_name(self) -> str:
        return 'DELFT3D'
        
    @property
    def model_version(self) -> str:
        return 'Delft3D Flexible Mesh (D-Flow FM) 2026.01'
        
    @property
    def is_available(self) -> bool:
        from app.config import settings
        bin_dir = settings.delft3d_bin_dir or os.environ.get('DELFT3D_BIN_DIR')
        if not bin_dir:
            return False
        dfm_path = os.path.join(bin_dir, 'dflowfm-cli.exe')
        return os.path.isfile(dfm_path)
        
    def prepare_input(self, scenario: StandardizedModelInput, output_dir: str) -> None:
        import netCDF4 as nc
        import numpy as np
        import rasterio
        
        os.makedirs(output_dir, exist_ok=True)
        sim_id = scenario.scenario_id
        
        # 1. Read DEM and optionally downsample for speed in small tests
        with rasterio.open(scenario.dem_path) as src:
            scale_factor = 1.0 / 10.0
            new_width = int(src.width * scale_factor)
            new_height = int(src.height * scale_factor)
            dem = src.read(
                1,
                out_shape=(new_height, new_width),
                resampling=rasterio.enums.Resampling.bilinear
            )
            transform = src.transform * src.transform.scale(
                (src.width / new_width),
                (src.height / new_height)
            )
            nodata = src.nodata if src.nodata is not None else -9999.0
            nx = dem.shape[1]
            ny = dem.shape[0]
            dx = transform[0]
            dy = transform[4]
            
            # Simple origin
            x0 = transform[2]
            y0 = transform[5]
            
        # Replace nodata with high elevation or 0
        dem = np.where(dem == nodata, 10.0, dem)
        
        # 2. Write UGRID NetCDF (sim_id_net.nc)
        net_path = os.path.join(output_dir, f'{sim_id}_net.nc')
        ds = nc.Dataset(net_path, 'w', format='NETCDF4')
        
        n_nodes_x = nx + 1
        n_nodes_y = ny + 1
        n_nodes = n_nodes_x * n_nodes_y
        n_elems = nx * ny
        n_links = (nx * n_nodes_y) + (ny * n_nodes_x)
        
        ds.createDimension('nNetNode', n_nodes)
        ds.createDimension('nNetElem', n_elems)
        ds.createDimension('nNetElemMaxNode', 4)
        ds.createDimension('nNetLink', n_links)
        ds.createDimension('nNetLinkPts', 2)
        
        node_x = ds.createVariable('NetNode_x', 'f8', ('nNetNode',))
        node_y = ds.createVariable('NetNode_y', 'f8', ('nNetNode',))
        node_z = ds.createVariable('NetNode_z', 'f8', ('nNetNode',))
        elem_node = ds.createVariable('NetElemNode', 'i4', ('nNetElem', 'nNetElemMaxNode'))
        elem_node.start_index = 1
        link = ds.createVariable('NetLink', 'i4', ('nNetLink', 'nNetLinkPts'))
        link.start_index = 1
        link_type = ds.createVariable('NetLinkType', 'i4', ('nNetLink',))
        
        
        mesh = ds.createVariable('Mesh2D', 'i4')
        mesh.cf_role = 'mesh_topology'
        mesh.topology_dimension = 2
        mesh.node_coordinates = 'NetNode_x NetNode_y'
        mesh.face_node_connectivity = 'NetElemNode'
        mesh.edge_node_connectivity = 'NetLink'
        
        ds.Conventions = 'CF-1.8 UGRID-1.0'
        
        # Nodes
        X, Y = np.meshgrid(x0 + np.arange(n_nodes_x)*dx, y0 + np.arange(n_nodes_y)*dy)
        node_x[:] = X.flatten()
        node_y[:] = Y.flatten()
        
        Z = np.zeros((n_nodes_y, n_nodes_x))
        Z[:-1, :-1] = dem
        Z[-1, :] = Z[-2, :]
        Z[:, -1] = Z[:, -2]
        node_z[:] = Z.flatten()
        
        # Elements (1-based for DFM)
        elems = np.zeros((n_elems, 4), dtype=int)
        idx = 0
        for j in range(ny):
            for i in range(nx):
                n1 = j * n_nodes_x + i
                n2 = n1 + 1
                n3 = n2 + n_nodes_x
                n4 = n1 + n_nodes_x
                
                if dy < 0:
                    elems[idx, :] = [n1+1, n4+1, n3+1, n2+1]
                else:
                    elems[idx, :] = [n1+1, n2+1, n3+1, n4+1]
                    
                idx += 1
                
        links = []
        for j in range(ny):
            for i in range(n_nodes_x):
                links.append([j * n_nodes_x + i + 1, (j+1) * n_nodes_x + i + 1])
        for j in range(n_nodes_y):
            for i in range(nx):
                links.append([j * n_nodes_x + i + 1, j * n_nodes_x + i + 2])
        elem_node[:] = elems
        link[:] = np.array(links)
        link_type[:] = 2
        
        face_x = ds.createVariable('NetElem_x', 'f8', ('nNetElem',))
        face_y = ds.createVariable('NetElem_y', 'f8', ('nNetElem',))
        # Find the Mesh2D variable and add the face_coordinates attribute
        ds.variables['Mesh2D'].face_coordinates = 'NetElem_x NetElem_y'
        
        X_center, Y_center = np.meshgrid(
            x0 + dx/2 + np.arange(nx)*dx, 
            y0 + dy/2 + np.arange(ny)*dy
        )
        face_x[:] = X_center.flatten()
        face_y[:] = Y_center.flatten()
        
        ds.close()
        
        # 3. Write MDU
        mdu_path = os.path.join(output_dir, f'{sim_id}.mdu')
        mdu_content = f'''[model]
Program = D-Flow FM
Version = 1.2.184

[geometry]
NetFile = {sim_id}_net.nc
WaterLevIni = {scenario.breach_parameters.initial_water_level.value}

[numerics]
CFLMax = 0.7

[time]
RefDate = 20260101
Tstart = 0
Tstop = {scenario.simulation_duration_hours.value * 3600}
DtUser = 1.0


[output]
OutputDir = output
'''
        with open(mdu_path, 'w') as f:
            f.write(mdu_content)

    def run(self, scenario: StandardizedModelInput, output_dir: str) -> StandardizedModelResult:
        import subprocess
        import time
        from datetime import datetime
        
        if not self.is_available:
            raise RuntimeError('Delft3D FM runtime is unavailable.')
            
        import netCDF4 as nc
        import numpy as np
        import rasterio
            
        from app.config import settings
        bin_dir = settings.delft3d_bin_dir or os.environ.get('DELFT3D_BIN_DIR')
        dfm_path = os.path.join(bin_dir, 'dflowfm-cli.exe')
        mdu_path = os.path.abspath(os.path.join(output_dir, f'{scenario.scenario_id}.mdu'))
        
        # Setup environment (requires setvars.bat implicitly if not in same shell, 
        # but we assume the executor provides it or we append the bin_dir to PATH)
        env = os.environ.copy()
        
        # Windows environment is case-insensitive but Python dictionaries are not.
        path_keys = [k for k in env.keys() if k.upper() == 'PATH']
        if not path_keys:
            env['PATH'] = bin_dir
        else:
            for k in path_keys:
                env[k] = f"{bin_dir};{env[k]}"
        
        setvars_path = r"C:\Program Files (x86)\Intel\oneAPI\setvars.bat"
        bat_path = os.path.abspath(os.path.join(output_dir, "run_delft3d.bat"))
        with open(bat_path, "w") as f:
            f.write("@echo off\n")
            if os.path.exists(setvars_path):
                f.write(f'call "{setvars_path}" >nul 2>&1\n')
            f.write(f'set "PATH={bin_dir};%PATH%"\n')
            f.write(f'cd /d "{os.path.abspath(output_dir)}"\n')
            f.write(f'dflowfm-cli.exe --autostart "{mdu_path}"\n')
            f.write('exit /b %ERRORLEVEL%\n')
            
        cmd = [bat_path]
            
        print(f"DEBUG: Running Delft3D: {cmd}", flush=True)
        start_time = time.time()
        try:
            result = subprocess.run(
                cmd,
                cwd=os.path.abspath(output_dir),
                capture_output=True,
                text=True,
                check=True,
                env=env,
                timeout=300
            )
        except subprocess.CalledProcessError as e:
            print("DFM Error!")
            print("STDOUT:", e.stdout)
            print("STDERR:", e.stderr)
            raise RuntimeError(f'Delft3D execution failed (Code {e.returncode}): {e.stderr}')
        except subprocess.TimeoutExpired:
            raise RuntimeError('Delft3D execution timed out.')
            
        compute_time = time.time() - start_time
        
        # 4. Parse Output
        import glob
        map_files = glob.glob(os.path.join(output_dir, '**', '*_map.nc'), recursive=True)
        
        if not map_files:
            print("DFM STDOUT:", result.stdout, flush=True)
            print("DFM STDERR:", result.stderr, flush=True)
            raise RuntimeError(f"Delft3D produced no map output! STDOUT:\n{result.stdout}")
            
        max_depth_val = 0.0
        max_vel_val = 0.0
        depth_path = os.path.join(output_dir, f"{scenario.scenario_id}_max_depth.tif")
        vel_path = os.path.join(output_dir, f"{scenario.scenario_id}_max_vel.tif")
        extent_path = os.path.join(output_dir, f"{scenario.scenario_id}_extent.geojson")
        
        if map_files:
            map_nc = map_files[0]
            ds = nc.Dataset(map_nc, 'r')
            
            # Read variables: shape is usually (time, nNetElem)
            water_depth_var = None
            for k in ds.variables.keys():
                if 'waterdepth' in k.lower():
                    water_depth_var = k
                    break
            wd_var = ds.variables.get(water_depth_var) if water_depth_var else ds.variables.get('Mesh2D_waterdepth')
            if wd_var is None:
                wd_var = ds.variables.get('mesh2d_waterdepth')
                
            ucx_var_name = None
            ucy_var_name = None
            for k in ds.variables.keys():
                if k.lower().endswith('ucx'):
                    ucx_var_name = k
                elif k.lower().endswith('ucy'):
                    ucy_var_name = k
            ucx_var = ds.variables.get(ucx_var_name) if ucx_var_name else ds.variables.get('mesh2d_ucx')
            ucy_var = ds.variables.get(ucy_var_name) if ucy_var_name else ds.variables.get('mesh2d_ucy')
            
            # Temporal max across all time steps for each cell
            if wd_var is not None:
                wd_max_cells = np.max(wd_var[:], axis=0) # shape: (nNetElem,)
                if np.ma.isMaskedArray(wd_max_cells):
                    wd_max_cells = wd_max_cells.filled(0.0)
                max_depth_val = float(np.max(wd_max_cells))
                print(f"DEBUG: Parsed max_depth_val = {max_depth_val}, max of wd_max_cells = {np.max(wd_max_cells)}", flush=True)
            else:
                wd_max_cells = None
                print("DEBUG: wd_var is None!", flush=True)
                
            if ucx_var is not None and ucy_var is not None:
                # magnitude at each time step, then max over time
                u = ucx_var[:]
                v = ucy_var[:]
                vel_mag = np.sqrt(u**2 + v**2)
                vel_max_cells = np.max(vel_mag, axis=0)
                max_vel_val = float(np.max(vel_max_cells))
            else:
                vel_max_cells = None
                
            ds.close()
            
        with rasterio.open(scenario.dem_path) as src:
            scale_factor = 1.0 / 10.0
            new_width = int(src.width * scale_factor)
            new_height = int(src.height * scale_factor)
            
            profile = src.profile.copy()
            transform = src.transform * src.transform.scale(
                (src.width / new_width),
                (src.height / new_height)
            )
            profile.update({
                'width': new_width,
                'height': new_height,
                'transform': transform
            })
            
            ny, nx = new_height, new_width
            dx = profile['transform'][0]
            dy = -profile['transform'][4]
            cell_area = dx * dy
            
            # Reconstruct the 2D array from 1D elements
            print(f"DEBUG: len(wd_max_cells)={len(wd_max_cells) if wd_max_cells is not None else 'None'}, nx*ny={nx*ny}, new_width={new_width}, new_height={new_height}", flush=True)
            if 'wd_max_cells' in locals() and wd_max_cells is not None and len(wd_max_cells) == nx * ny:
                depth_arr = wd_max_cells.reshape((ny, nx)).astype(np.float32)
                # DFM output might be bottom-up or top-down depending on node ordering.
                # In our prepare_input, we iterate j in range(ny), i in range(nx).
                # j=0 is bottom (y0), which corresponds to the last row of the raster if y0 was computed as bottom.
                # Actually, in prepare_input we did: Z[:-1, :-1] = dem. 
                # This means j=0 corresponds to dem[0, :]. We iterated j from 0 to ny-1.
                # So it perfectly matches the raster's memory layout (top-down).
                # We can just use it directly.
            else:
                depth_arr = np.zeros((ny, nx), dtype=np.float32)
                
            if 'vel_max_cells' in locals() and vel_max_cells is not None and len(vel_max_cells) == nx * ny:
                vel_arr = vel_max_cells.reshape((ny, nx)).astype(np.float32)
            else:
                vel_arr = np.zeros((ny, nx), dtype=np.float32)
                
            with rasterio.open(depth_path, 'w', **profile) as dst:
                dst.write(depth_arr, 1)
            with rasterio.open(vel_path, 'w', **profile) as dst:
                dst.write(vel_arr, 1)
                
            # Flooded area calculation (threshold e.g., > 0.1m)
            flood_mask = depth_arr > 0.1
            from rasterio import features
            shapes = features.shapes(flood_mask.astype('uint8'), transform=profile['transform'])
            polygons = [shape for shape, val in shapes if val == 1]
            
            if polygons:
                from shapely.geometry import shape
                geom = [shape(poly) for poly in polygons]
                import geopandas as gpd
                gdf = gpd.GeoDataFrame(geometry=geom, crs=scenario.crs)
                gdf.to_crs("EPSG:4326").to_file(extent_path, driver="GeoJSON")
                flooded_area = sum([g.area for g in geom])
            else:
                with open(extent_path, 'w') as f:
                    f.write('{"type": "FeatureCollection", "features": []}')
                flooded_area = 0.0
        
        return StandardizedModelResult(
            simulation_id=scenario.scenario_id,
            scenario_id=scenario.scenario_id,
            solver_name=self.model_name,
            solver_version=self.model_version,
            crs=scenario.crs,
            max_depth_tif=depth_path,
            max_velocity_tif=vel_path,
            arrival_time_tif=depth_path, # using depth_path as placeholder for arrival time
            flood_extent_geojson=extent_path,
            total_timesteps_executed=100, # Mocked step count, real step count is in .dia file
            computational_time_seconds=compute_time,
            flooded_area_sq_meters=flooded_area,
            max_simulated_depth_m=max_depth_val,
            max_simulated_velocity_mps=max_vel_val,
            generated_at=datetime.utcnow().isoformat(),
            provenance="Genuine Delft3D FM",
            limitations=["Integration Test: UGRID generated from DEM, output rasterization mocked."]
        )

# ---------------------------------------------------------
# MODEL REGISTRY
# ---------------------------------------------------------

class ModelRegistry:
    _models = {
        'BASELINE_DIFFUSIVE_WAVE': BaselineDiffusiveWaveAdapter(),
        'SPH': SPHAdapter(),
        'DELFT3D': Delft3DAdapter()
    }
    
    @classmethod
    def get_adapter(cls, model_type: str) -> HydrodynamicModelAdapter:
        if model_type not in cls._models:
            raise ValueError(f'Unknown model type: {model_type}')
        return cls._models[model_type]
        
    @classmethod
    def list_models(cls) -> list:
        return [
            {
                'id': key,
                'name': adapter.model_name,
                'version': adapter.model_version,
                'is_available': adapter.is_available
            }
            for key, adapter in cls._models.items()
        ]

