import os
import requests
import json
import logging
from typing import Dict, Any, Tuple

# Attempt to import geospatial libraries, allow failure for environments without GDAL binaries
try:
    import rasterio
    from rasterio.merge import merge
    from rasterio.mask import mask
    from rasterio.io import MemoryFile
    from shapely.geometry import box, mapping
    from pyproj import Transformer
    GIS_AVAILABLE = True
except ImportError as e:
    GIS_AVAILABLE = False
    logging.warning(f"GIS libraries not fully available: {e}. DEM processing will run in degraded/mock mode.")

logger = logging.getLogger(__name__)

class DEMProcessor:
    def __init__(self, output_dir: str = "data/dem"):
        self.output_dir = output_dir
        self.stac_url = "https://earth-search.aws.element84.com/v1"
        self.collection = "cop-dem-glo-30"
        os.makedirs(self.output_dir, exist_ok=True)

    def define_aoi(self, lat: float, lon: float, buffer_degrees: float = 0.2) -> Tuple[float, float, float, float]:
        """
        Defines an Area of Interest (AOI) bounding box around a point.
        buffer_degrees of 0.2 is roughly 22km, covering a reasonable downstream corridor.
        Returns: (min_lon, min_lat, max_lon, max_lat)
        """
        min_lon = lon - buffer_degrees
        max_lon = lon + buffer_degrees
        min_lat = lat - buffer_degrees
        max_lat = lat + buffer_degrees
        return (min_lon, min_lat, max_lon, max_lat)

    def discover_dem_data(self, bbox: Tuple[float, float, float, float]) -> list:
        """
        Queries the STAC API to find Copernicus DEM tiles intersecting the AOI.
        """
        logger.info(f"Querying STAC API {self.stac_url} for bbox {bbox}")
        
        # In sandboxed environments without proper SSL certs, allow disabling verification
        verify_ssl = os.environ.get("VERIFY_SSL", "True").lower() == "true"
        if not verify_ssl:
            from urllib3.exceptions import InsecureRequestWarning
            requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
            
        search_url = f"{self.stac_url}/search"
        payload = {
            "collections": [self.collection],
            "bbox": list(bbox),
            "limit": 100
        }
        
        response = requests.post(search_url, json=payload, verify=verify_ssl)
        response.raise_for_status()
        
        feature_collection = response.json()
        items = feature_collection.get("features", [])
        logger.info(f"Discovered {len(items)} DEM tiles.")
        
        assets = []
        for item in items:
            if "assets" in item and "data" in item["assets"]:
                url = item["assets"]["data"]["href"]
                # Convert s3:// to direct https:// for requests compatibility
                if url.startswith("s3://copernicus-dem-30m/"):
                    url = url.replace("s3://copernicus-dem-30m/", "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com/")
                assets.append({"id": item["id"], "url": url})
                
        return assets

    def download_tile(self, asset: Dict[str, str]) -> str:
        """
        Downloads a single DEM tile via HTTP.
        """
        filename = f"{asset['id']}.tif"
        filepath = os.path.join(self.output_dir, filename)
        
        if os.path.exists(filepath):
            logger.info(f"Tile {filename} already downloaded.")
            return filepath
            
        verify_ssl = os.environ.get("VERIFY_SSL", "True").lower() == "true"
        logger.info(f"Downloading DEM tile: {asset['url']}")
        response = requests.get(asset['url'], stream=True, verify=verify_ssl, timeout=(10, 30))
        if response.status_code == 200:
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return filepath
        else:
            raise Exception(f"Failed to download tile: HTTP {response.status_code}")

    def process_dem(self, lat: float, lon: float, name: str, buffer_degrees: float = 0.2) -> Dict[str, Any]:
        """
        Full pipeline: Define AOI, discover, download, mosaic, clip, and extract metadata.
        """
        bbox = self.define_aoi(lat, lon, buffer_degrees)
        
        # 1. Discover
        assets = self.discover_dem_data(bbox)
        if not assets:
            raise Exception("No DEM data found for the given AOI.")
            
        # 2. Download
        downloaded_files = []
        for asset in assets:
            try:
                filepath = self.download_tile(asset)
                downloaded_files.append(filepath)
            except Exception as e:
                logger.error(f"Error downloading {asset['id']}: {e}")
                
        if not downloaded_files:
            raise Exception("Failed to download any DEM tiles.")
            
        # 3. Process (if GIS libraries available)
        output_filepath = os.path.join(self.output_dir, f"{name.replace(' ', '_')}_dem.tif")
        
        if not GIS_AVAILABLE:
            logger.warning("Returning raw tiles without merging/clipping due to missing GIS libraries.")
            return {
                "source": "Copernicus GLO-30 via Earth Search",
                "status": "partial_success_no_gdal",
                "raw_files": downloaded_files,
                "bbox": bbox
            }
            
        # Mosaic & Clip
        logger.info("Mosaicing and clipping downloaded DEM tiles...")
        src_files_to_mosaic = []
        for fp in downloaded_files:
            src = rasterio.open(fp)
            src_files_to_mosaic.append(src)
            
        mosaic, out_trans = merge(src_files_to_mosaic)
        
        # Create Shapely Polygon for clipping
        aoi_polygon = box(*bbox)
        
        # Write merged mosaic to memory for masking
        meta = src.meta.copy()
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
                
        # Close source files
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
            
        # Extract metadata and stats
        with rasterio.open(output_filepath) as src:
            data = src.read(1)
            valid_data = data[data != src.nodata]
            
            stats = {
                "min_elevation_m": float(valid_data.min()) if valid_data.size > 0 else 0,
                "max_elevation_m": float(valid_data.max()) if valid_data.size > 0 else 0,
                "mean_elevation_m": float(valid_data.mean()) if valid_data.size > 0 else 0,
                "crs": src.crs.to_string(),
                "resolution": src.res
            }
            
        return {
            "source": "Copernicus GLO-30 via Earth Search",
            "status": "success",
            "output_file": output_filepath,
            "bbox": bbox,
            "metadata": stats
        }
