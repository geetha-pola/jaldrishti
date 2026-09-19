import os
import json
import logging
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from pyproj import Proj, transform, Transformer
import geopandas as gpd
from shapely.geometry import Point, LineString, box
import warnings

try:
    from pysheds.grid import Grid
    PYSHEDS_AVAILABLE = True
except ImportError:
    PYSHEDS_AVAILABLE = False

logger = logging.getLogger(__name__)

class TerrainAnalyzer:
    def __init__(self, output_dir: str = "data/domain"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        
    def _get_utm_epsg(self, lat: float, lon: float) -> str:
        """Calculates the UTM EPSG code for a given lat/lon."""
        utm_zone = int((lon + 180) / 6) + 1
        is_northern = lat >= 0
        epsg_code = 32600 + utm_zone if is_northern else 32700 + utm_zone
        return f"EPSG:{epsg_code}"

    def reproject_dem_to_utm(self, input_dem: str, lat: float, lon: float) -> str:
        """Reprojects the DEM to UTM to allow metric distance calculations."""
        utm_epsg = self._get_utm_epsg(lat, lon)
        output_dem = os.path.join(self.output_dir, "projected_dem.tif")
        
        with rasterio.open(input_dem) as src:
            transform, width, height = calculate_default_transform(
                src.crs, utm_epsg, src.width, src.height, *src.bounds)
            kwargs = src.meta.copy()
            kwargs.update({
                'crs': utm_epsg,
                'transform': transform,
                'width': width,
                'height': height,
                'nodata': src.nodata or 0.0 # Handle missing nodata
            })

            with rasterio.open(output_dem, 'w', **kwargs) as dst:
                for i in range(1, src.count + 1):
                    reproject(
                        source=rasterio.band(src, i),
                        destination=rasterio.band(dst, i),
                        src_transform=src.transform,
                        src_crs=src.crs,
                        dst_transform=transform,
                        dst_crs=utm_epsg,
                        resampling=Resampling.bilinear)
                        
        logger.info(f"Reprojected DEM to {utm_epsg}")
        return output_dem, utm_epsg

    def analyze_terrain(self, dem_path: str, source_lat: float, source_lon: float, corridor_width_m: float = 2000.0) -> dict:
        """
        Derives terrain metrics, flow networks, and downstream corridor.
        """
        if not PYSHEDS_AVAILABLE:
            raise Exception("pysheds is required for terrain analysis.")
            
        # 1. Reproject DEM to local UTM for accurate metric processing
        utm_dem_path, utm_epsg = self.reproject_dem_to_utm(dem_path, source_lat, source_lon)
        
        # Determine UTM coordinates of the source (dam)
        transformer = Transformer.from_crs("EPSG:4326", utm_epsg, always_xy=True)
        source_x, source_y = transformer.transform(source_lon, source_lat)
        
        # 2. Load into pysheds Grid
        # Ignore pysheds warnings about projections
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            grid = Grid.from_raster(utm_dem_path)
            dem = grid.read_raster(utm_dem_path)
        
        # Handle NoData properly. Copernicus 0.0m is often ocean or NoData masked as 0. 
        # In a real DEM, 0 can be valid near coast, but in Idukki it's likely a missing pixel or outside bounds.
        # We will set 0 to np.nan for internal routing if it's the nodata value.
        nodata = dem.nodata
        if nodata is None:
            nodata = 0.0
        
        dem_masked = np.where((dem == nodata) | (dem <= 0.0), np.nan, dem)
        
        # 3. Fill depressions and resolve flats to create hydrologically correct DEM
        logger.info("Filling depressions...")
        filled_dem = grid.fill_pits(dem)
        resolved_dem = grid.resolve_flats(filled_dem)
        
        # 4. Compute Flow Direction (D8 routing)
        logger.info("Computing flow direction...")
        # D8 directional mapping: N:64, NE:128, E:1, SE:2, S:4, SW:8, W:16, NW:32
        dirmap = (64, 128, 1, 2, 4, 8, 16, 32)
        fdir = grid.flowdir(resolved_dem, dirmap=dirmap)
        
        # 5. Compute Flow Accumulation
        logger.info("Computing flow accumulation...")
        acc = grid.accumulation(fdir, dirmap=dirmap)
        
        # 6. Extract downstream flow path from the dam
        logger.info(f"Extracting downstream path from dam at UTM: ({source_x}, {source_y})")
        # Snap dam location to the highest accumulation pixel within a small radius (e.g. 5 pixels)
        # to ensure the dam falls exactly on the river network.
        try:
            snapped_x, snapped_y = grid.snap_to_mask(acc > 100, (source_x, source_y), return_dist=False)
        except Exception:
            snapped_x, snapped_y = source_x, source_y
            
        # Delineate catchment or extract river
        # Actually, to get the downstream corridor, we trace the flow direction downstream from the snapped dam pixel.
        # Pysheds doesn't have a direct "trace downstream" function exposed easily without delineating a catchment.
        # But we can extract the river network for the whole DEM and filter it.
        # Or we can just calculate the catchment of the *outlet* of the DEM that includes our dam.
        # For simplicity, if we want the downstream flood area, we can threshold the accumulation to find rivers,
        # and create a buffer around the downstream segment.
        
        # Let's extract all river networks above a certain accumulation threshold (e.g., 500 pixels)
        branches = grid.extract_river_network(fdir, acc > 500, dirmap=dirmap)
        
        # Instead of manual graph traversal to find the exact downstream path from the dam,
        # a generalized approach for flood domain is to define the basin downstream of the dam.
        # Since water flows downstream, we can find the catchment for the entire DEM,
        # and intersect it with rivers.
        # A simpler robust approach for creating the *domain*: 
        # Convert the high-accumulation pixels into a GeoDataFrame, and buffer them.
        
        # 7. Create simulation domain polygon (Downstream Corridor)
        # Convert branches to Shapely LineStrings
        lines = []
        if branches and 'features' in branches:
            for feature in branches['features']:
                geom = feature['geometry']
                if geom['type'] == 'LineString':
                    lines.append(LineString(geom['coordinates']))
                    
        river_gdf = gpd.GeoDataFrame(geometry=lines, crs=utm_epsg)
        
        # Buffer the river network by the corridor width
        logger.info(f"Generating domain buffer of {corridor_width_m} meters around primary rivers")
        buffered_rivers = river_gdf.geometry.buffer(corridor_width_m)
        domain_polygon = buffered_rivers.unary_union
        
        # If the domain is a MultiPolygon, we keep the largest contiguous area or the one intersecting the dam.
        domain_gdf = gpd.GeoDataFrame(geometry=[domain_polygon], crs=utm_epsg)
        
        # Ensure the dam is within the domain
        dam_point = Point(source_x, source_y)
        domain_gdf = domain_gdf[domain_gdf.geometry.intersects(dam_point.buffer(corridor_width_m*2))]
        
        if domain_gdf.empty:
            logger.warning("Dam point did not intersect the extracted river network perfectly. Using fallback buffer.")
            domain_gdf = gpd.GeoDataFrame(geometry=[dam_point.buffer(corridor_width_m * 5)], crs=utm_epsg)
            
        final_domain_polygon = domain_gdf.geometry.iloc[0]
        domain_bounds = final_domain_polygon.bounds # (minx, miny, maxx, maxy)
        
        # 8. Compute Slope
        logger.info("Computing terrain slope...")
        slope = np.gradient(dem) # Rough slope approximation for diagnostic
        slope_mag = np.sqrt(slope[0]**2 + slope[1]**2)
        
        stats = {
            "elevation_min": float(np.nanmin(dem_masked)),
            "elevation_max": float(np.nanmax(dem_masked)),
            "elevation_mean": float(np.nanmean(dem_masked)),
            "slope_mean": float(np.nanmean(slope_mag)),
            "accumulation_max": float(np.nanmax(acc)),
            "nodata_pixels_handled": int(np.sum(np.isnan(dem_masked)))
        }
        
        # 9. Save outputs
        fdir_path = os.path.join(self.output_dir, "flow_direction.tif")
        acc_path = os.path.join(self.output_dir, "flow_accumulation.tif")
        domain_path = os.path.join(self.output_dir, "simulation_domain.geojson")
        
        # We need the profile from the projected DEM to save our numpy arrays
        with rasterio.open(utm_dem_path) as src:
            profile = src.profile
            
        profile.update(dtype=rasterio.float32, count=1, compress='deflate')
        
        with rasterio.open(fdir_path, 'w', **profile) as dst:
            dst.write(fdir.astype(rasterio.float32), 1)
            
        with rasterio.open(acc_path, 'w', **profile) as dst:
            dst.write(acc.astype(rasterio.float32), 1)
        
        # Save domain
        # Reproject back to 4326 for GeoJSON standard
        domain_gdf_4326 = domain_gdf.to_crs("EPSG:4326")
        domain_gdf_4326.to_file(domain_path, driver="GeoJSON")
        
        return {
            "status": "success",
            "crs": utm_epsg,
            "corridor_width_m": corridor_width_m,
            "stats": stats,
            "domain_geojson": domain_path,
            "fdir_tif": fdir_path,
            "acc_tif": acc_path,
            "projected_dem": utm_dem_path,
            "domain_bounds_utm": domain_bounds
        }
