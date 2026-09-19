import os
import json
import logging
import requests
from datetime import datetime
from typing import Dict, Any, Tuple, Optional
from dataclasses import dataclass

try:
    import rasterio
    from rasterio.merge import merge
    from rasterio.mask import mask
    from rasterio.io import MemoryFile
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    from shapely.geometry import box, mapping
    from pyproj import Transformer
    GIS_AVAILABLE = True
except ImportError as e:
    GIS_AVAILABLE = False
    logging.warning(f"GIS libraries not fully available: {e}. DEM processing will run in degraded mode.")

logger = logging.getLogger(__name__)

@dataclass
class DEMConfig:
    """Clear configuration for DEM acquisition and processing."""
    output_dir: str = "data/dem"
    buffer_degrees: float = 0.2 # ~22km radius, large enough for downstream modelling
    target_crs: str = "EPSG:4326" # Default CRS, can be changed to UTM (e.g. EPSG:32643)
    target_resolution: Optional[float] = None
    stac_url: str = "https://earth-search.aws.element84.com/v1"
    collection: str = "cop-dem-glo-30"

class DEMProcessor:
    def __init__(self, config: DEMConfig = DEMConfig()):
        self.config = config
        os.makedirs(self.config.output_dir, exist_ok=True)

    def define_aoi(self, lat: float, lon: float) -> Tuple[float, float, float, float]:
        """
        Defines an Area of Interest (AOI) bounding box around a point using the configured buffer.
        """
        min_lon = lon - self.config.buffer_degrees
        max_lon = lon + self.config.buffer_degrees
        min_lat = lat - self.config.buffer_degrees
        max_lat = lat + self.config.buffer_degrees
        return (min_lon, min_lat, max_lon, max_lat)

    def discover_dem_data(self, bbox: Tuple[float, float, float, float]) -> list:
        verify_ssl = os.environ.get("VERIFY_SSL", "True").lower() == "true"
        if not verify_ssl:
            from urllib3.exceptions import InsecureRequestWarning
            requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
            
        search_url = f"{self.config.stac_url}/search"
        payload = {
            "collections": [self.config.collection],
            "bbox": list(bbox),
            "limit": 100
        }
        
        response = requests.post(search_url, json=payload, verify=verify_ssl)
        response.raise_for_status()
        
        feature_collection = response.json()
        items = feature_collection.get("features", [])
        
        assets = []
        for item in items:
            if "assets" in item and "data" in item["assets"]:
                url = item["assets"]["data"]["href"]
                if url.startswith("s3://copernicus-dem-30m/"):
                    url = url.replace("s3://copernicus-dem-30m/", "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com/")
                assets.append({"id": item["id"], "url": url})
                
        return assets

    def download_tile(self, asset: Dict[str, str]) -> str:
        filename = f"{asset['id']}.tif"
        filepath = os.path.join(self.config.output_dir, filename)
        
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            return filepath
            
        verify_ssl = os.environ.get("VERIFY_SSL", "True").lower() == "true"
        response = requests.get(asset['url'], stream=True, verify=verify_ssl, timeout=(10, 30))
        if response.status_code == 200:
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return filepath
        else:
            raise Exception(f"Failed to download tile: HTTP {response.status_code}")

    def save_metadata(self, metadata: Dict[str, Any], filepath: str):
        """Stores DEM metadata and provenance alongside the raster."""
        with open(filepath, 'w') as f:
            json.dump(metadata, f, indent=4)

    def process_dem(self, lat: float, lon: float, name: str, local_files: list = None) -> Dict[str, Any]:
        """
        Full pipeline: Define AOI, discover, download (or use local), mosaic, clip, and extract metadata.
        """
        bbox = self.define_aoi(lat, lon)
        downloaded_files = local_files or []
        
        if not local_files:
            assets = self.discover_dem_data(bbox)
            if not assets:
                raise Exception("No DEM data found for the given AOI.")
            
            for asset in assets:
                try:
                    filepath = self.download_tile(asset)
                    downloaded_files.append(filepath)
                except Exception as e:
                    logger.error(f"Error downloading {asset['id']}: {e}")
                    
            if not downloaded_files:
                raise Exception("Failed to download any DEM tiles.")
            
        output_filepath = os.path.join(self.config.output_dir, f"{name.replace(' ', '_')}_dem.tif")
        metadata_filepath = output_filepath.replace('.tif', '.json')
        
        if not GIS_AVAILABLE:
            raise Exception("GIS libraries not available to process DEM.")
            
        # Mosaic
        src_files_to_mosaic = [rasterio.open(fp) for fp in downloaded_files]
        mosaic, out_trans = merge(src_files_to_mosaic)
        
        # Clip
        aoi_polygon = box(*bbox)
        meta = src_files_to_mosaic[0].meta.copy()
        meta.update({
            "driver": "GTiff",
            "height": mosaic.shape[1],
            "width": mosaic.shape[2],
            "transform": out_trans
        })
        
        with MemoryFile() as memfile:
            with memfile.open(**meta) as dataset:
                dataset.write(mosaic)
            with memfile.open() as dataset:
                out_image, out_transform = mask(dataset, [mapping(aoi_polygon)], crop=True)
                out_meta = dataset.meta.copy()
                
        for src in src_files_to_mosaic:
            src.close()
            
        out_meta.update({
            "driver": "GTiff",
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform
        })
        
        with rasterio.open(output_filepath, "w", **out_meta) as dest:
            dest.write(out_image)
            
        # Validate and extract stats
        with rasterio.open(output_filepath) as src:
            data = src.read(1)
            valid_data = data[data != src.nodata]
            
            stats = {
                "min_elevation_m": float(valid_data.min()) if valid_data.size > 0 else 0,
                "max_elevation_m": float(valid_data.max()) if valid_data.size > 0 else 0,
                "mean_elevation_m": float(valid_data.mean()) if valid_data.size > 0 else 0,
            }
            resolution = src.res
            crs = src.crs.to_string()
            
        metadata = {
            "source": "Copernicus GLO-30 via Earth Search",
            "acquisition_date": datetime.utcnow().isoformat(),
            "resolution": resolution,
            "crs": crs,
            "bounding_box": bbox,
            "file_name": os.path.basename(output_filepath),
            "elevation_statistics": stats
        }
        
        self.save_metadata(metadata, metadata_filepath)
            
        return {
            "status": "success",
            "output_file": output_filepath,
            "metadata_file": metadata_filepath,
            "metadata": metadata
        }
