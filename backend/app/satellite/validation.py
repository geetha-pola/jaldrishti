import os
import json
import logging
from datetime import datetime, timedelta
import geopandas as gpd
from shapely.geometry import Polygon

# Try to import earth engine, but gracefully handle if not installed or configured
try:
    import ee
    EE_AVAILABLE = True
except ImportError:
    ee = None
    EE_AVAILABLE = False

class SatelliteValidator:
    def __init__(self, output_dir="data/satellite_results"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.ee_initialized = False
        
        if EE_AVAILABLE:
            try:
                # Attempt to initialize Earth Engine without explicit credentials
                # This requires the host machine to be authenticated via `earthengine authenticate`
                ee.Initialize()
                self.ee_initialized = True
            except Exception as e:
                logging.warning(f"Google Earth Engine initialization failed: {e}. "
                                "GEE credentials/authentication are required for live satellite fetching.")
    
    def calculate_metrics(self, modeled_gdf: gpd.GeoDataFrame, observed_gdf: gpd.GeoDataFrame) -> dict:
        """Calculates area, intersection, IoU, precision, and recall between modelled and observed."""
        if modeled_gdf.empty or observed_gdf.empty:
            return {
                "modeled_area_km2": modeled_gdf.geometry.area.sum() / 1e6 if not modeled_gdf.empty else 0.0,
                "observed_area_km2": observed_gdf.geometry.area.sum() / 1e6 if not observed_gdf.empty else 0.0,
                "intersection_area_km2": 0.0,
                "iou": 0.0,
                "precision": 0.0,
                "recall": 0.0
            }
            
        # Ensure consistent CRS (using an equal area or UTM projection for accurate area)
        target_crs = modeled_gdf.crs
        if observed_gdf.crs != target_crs:
            observed_gdf = observed_gdf.to_crs(target_crs)
            
        # Calculate individual areas
        mod_area = modeled_gdf.geometry.area.sum() / 1e6
        obs_area = observed_gdf.geometry.area.sum() / 1e6
        
        # Calculate intersection
        intersection = gpd.overlay(modeled_gdf, observed_gdf, how='intersection')
        int_area = intersection.geometry.area.sum() / 1e6
        
        # Calculate union
        union_area = mod_area + obs_area - int_area
        
        # Metrics
        iou = (int_area / union_area) * 100 if union_area > 0 else 0.0
        precision = (int_area / mod_area) * 100 if mod_area > 0 else 0.0
        recall = (int_area / obs_area) * 100 if obs_area > 0 else 0.0
        
        return {
            "modeled_area_km2": float(mod_area),
            "observed_area_km2": float(obs_area),
            "intersection_area_km2": float(int_area),
            "iou": float(iou),
            "precision": float(precision),
            "recall": float(recall)
        }

    def fetch_sentinel1_flood_mask(self, bounds: tuple, event_date: str):
        """
        Queries Sentinel-1 SAR GRD in Google Earth Engine to derive a water mask.
        Returns a GeoDataFrame of the observed flood extent.
        """
        if not self.ee_initialized:
            raise RuntimeError("Earth Engine is not initialized. Cannot fetch Sentinel-1 data.")
            
        # Convert bounds (minx, miny, maxx, maxy) to EE geometry
        minx, miny, maxx, maxy = bounds
        roi = ee.Geometry.Rectangle([minx, miny, maxx, maxy])
        
        # Date windows
        try:
            event_dt = datetime.fromisoformat(event_date.replace("Z", "+00:00"))
        except ValueError:
            event_dt = datetime.strptime(event_date, "%Y-%m-%d")
            
        pre_start = (event_dt - timedelta(days=15)).strftime("%Y-%m-%d")
        pre_end = event_dt.strftime("%Y-%m-%d")
        post_start = event_dt.strftime("%Y-%m-%d")
        post_end = (event_dt + timedelta(days=5)).strftime("%Y-%m-%d")
        
        # Query S1 GRD
        collection = ee.ImageCollection('COPERNICUS/S1_GRD') \
            .filterBounds(roi) \
            .filter(ee.Filter.eq('instrumentMode', 'IW')) \
            .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
            
        pre_img = collection.filterDate(pre_start, pre_end).select('VH').median()
        post_img = collection.filterDate(post_start, post_end).select('VH').median()
        
        # Simple change detection for flood (significant drop in backscatter)
        # Ratio = post / pre. In dB: post - pre
        ratio = post_img.subtract(pre_img)
        # Threshold: drop of more than 3 dB and post backscatter < -18 dB (water surface)
        flood_mask = ratio.lt(-3).And(post_img.lt(-18))
        flood_mask = flood_mask.updateMask(flood_mask) # Keep only water pixels
        
        # Vectorize
        vectors = flood_mask.reduceToVectors(
            geometry=roi,
            crs='EPSG:4326',
            scale=30,
            geometryType='polygon',
            eightConnected=False,
            maxPixels=1e8
        )
        
        # Fetch features locally
        features = vectors.getInfo()['features']
        
        if not features:
            return gpd.GeoDataFrame(columns=['geometry'], crs="EPSG:4326")
            
        from shapely.geometry import shape
        geoms = [shape(f['geometry']) for f in features]
        return gpd.GeoDataFrame(geometry=geoms, crs="EPSG:4326")

    def validate_simulation(self, sim_id: str, modeled_extent_path: str, event_date: str = None) -> dict:
        """
        Compares modeled flood extent with satellite observations.
        """
        # Load Modeled Extent
        if not os.path.exists(modeled_extent_path):
            raise FileNotFoundError(f"Modeled extent not found at {modeled_extent_path}")
            
        modeled_gdf = gpd.read_file(modeled_extent_path)
        if modeled_gdf.empty:
            raise ValueError("Modeled extent is empty.")
            
        summary = {
            "simulation_id": sim_id,
            "satellite_source": "Sentinel-1",
            "validation_status": "NOT AVAILABLE",
            "pre_event_date": None,
            "post_event_date": None,
            "modeled_area_km2": 0.0,
            "observed_area_km2": 0.0,
            "intersection_area_km2": 0.0,
            "iou": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "limitations": [
                "MODEL SCENARIO STATUS: The current simulation is a '2D Diffusive Wave Baseline Simulation of an Extreme Hypothetical Stress-Test Scenario'.",
                "SATELLITE OBSERVATION: Satellite imagery is used as a reference observation, NOT as absolute 'ground truth'.",
                "PHYSICAL ACCURACY: Satellite validation quantifies spatial agreement, but does not prove the baseline solver is a fully validated physical representation (like SWE, SPH, or Delft3D)."
            ]
        }
        
        # Modeled Area (using equal area projection)
        target_crs = modeled_gdf.crs
        # Fallback to UTM if it's geographic
        if target_crs.is_geographic:
            # simple projection based on bounds for area calc
            # Or just use the EPSG:32643 we know Idukki uses.
            modeled_gdf = modeled_gdf.to_crs("EPSG:32643")
            
        summary["modeled_area_km2"] = modeled_gdf.geometry.area.sum() / 1e6
        
        if not event_date:
            summary["validation_status"] = "NO SUITABLE SATELLITE OBSERVATION AVAILABLE FOR THIS SCENARIO"
            summary["limitations"].append("HYPOTHETICAL EVENT: No real-world event date was provided for this hypothetical scenario.")
            self._save_summary(sim_id, summary)
            return summary
            
        if not self.ee_initialized:
            summary["validation_status"] = "NOT AVAILABLE"
            summary["limitations"].append("GEE AUTHENTICATION: Google Earth Engine credentials are required but not found in this environment.")
            self._save_summary(sim_id, summary)
            return summary
            
        try:
            # Convert modeled_gdf to 4326 for GEE bounds
            bounds_4326 = modeled_gdf.to_crs("EPSG:4326").total_bounds
            
            # Fetch satellite observation
            observed_gdf_4326 = self.fetch_sentinel1_flood_mask(bounds_4326, event_date)
            
            if observed_gdf_4326.empty:
                summary["validation_status"] = "NO FLOOD OBSERVED IN SATELLITE IMAGERY"
                self._save_summary(sim_id, summary)
                return summary
                
            # Project to match modeled
            observed_gdf = observed_gdf_4326.to_crs(modeled_gdf.crs)
            
            # Calculate metrics
            metrics = self.calculate_metrics(modeled_gdf, observed_gdf)
            summary.update(metrics)
            
            # Event dates used in query
            event_dt = datetime.strptime(event_date, "%Y-%m-%d") if "T" not in event_date else datetime.fromisoformat(event_date.replace("Z", "+00:00"))
            summary["pre_event_date"] = (event_dt - timedelta(days=15)).strftime("%Y-%m-%d")
            summary["post_event_date"] = event_dt.strftime("%Y-%m-%d")
            
            if summary["iou"] > 0:
                summary["validation_status"] = "PARTIAL" if summary["iou"] < 50 else "VALIDATED"
            else:
                summary["validation_status"] = "NO SPATIAL AGREEMENT"
                
            # Save the satellite mask for visualization
            out_mask = os.path.join(self.output_dir, f"{sim_id}_satellite_mask.geojson")
            observed_gdf_4326.to_file(out_mask, driver="GeoJSON")
            
        except Exception as e:
            logging.error(f"Satellite validation failed: {e}")
            summary["validation_status"] = "FAILED"
            summary["limitations"].append(f"EXECUTION ERROR: {str(e)}")
            
        self._save_summary(sim_id, summary)
        return summary
        
    def _save_summary(self, sim_id, summary):
        out_path = os.path.join(self.output_dir, f"{sim_id}_satellite_validation.json")
        with open(out_path, 'w') as f:
            json.dump(summary, f, indent=4)
