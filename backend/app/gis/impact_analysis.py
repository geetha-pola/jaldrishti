import os
import json
import uuid
import time
import requests
import urllib3
import numpy as np
import rasterio
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon, shape
from datetime import datetime

# Handle SSL context for strict Windows environments
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
VERIFY_SSL = os.environ.get("VERIFY_SSL", "False").lower() in ["true", "1", "t"]

class ImpactAnalyzer:
    def __init__(self, extent_path: str, depth_path: str, arrival_path: str, output_dir: str = "data/impact_results"):
        self.extent_path = extent_path
        self.depth_path = depth_path
        self.arrival_path = arrival_path
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Load the simulated flood extent
        self.extent_gdf = gpd.read_file(self.extent_path)
        if self.extent_gdf.empty:
            raise ValueError("Flood extent is empty. Cannot perform impact analysis.")
            
        with rasterio.open(self.depth_path) as src:
            self.crs = src.crs.to_string()
            
        self.extent_gdf = self.extent_gdf.to_crs(self.crs)
        
    def fetch_osm_data(self) -> dict:
        """Fetches infrastructure data from Overpass API within the bounding box."""
        # Convert extent to 4326 for Overpass
        extent_4326 = self.extent_gdf.to_crs("EPSG:4326")
        minx, miny, maxx, maxy = extent_4326.total_bounds
        
        # Overpass bbox format: south,west,north,east
        bbox = f"{miny},{minx},{maxy},{maxx}"
        
        overpass_url = "https://overpass-api.de/api/interpreter"
        query = f"""
        [out:json][timeout:60];
        (
          way["highway"]({bbox});
          node["bridge"="yes"]({bbox});
          way["bridge"="yes"]({bbox});
          way["building"]({bbox});
          node["place"]({bbox});
          node["amenity"="school"]({bbox});
          node["amenity"="hospital"]({bbox});
        );
        out body geom;
        """
        
        try:
            print("Querying Overpass API for real infrastructure data...")
            headers = {'User-Agent': 'Jaldrishti/1.0 (Research Project)'}
            response = requests.post(overpass_url, data={'data': query}, headers=headers, verify=VERIFY_SSL, timeout=60)
            response.raise_for_status()
            data = response.json()
            print(f"OSM returned {len(data.get('elements', []))} raw elements.")
            return data
        except Exception as e:
            print(f"WARNING: Failed to fetch OSM data due to network/API error: {e}")
            return {"elements": []}

    def parse_osm_elements(self, data: dict):
        """Converts OSM JSON into GeoDataFrames by category."""
        roads = []
        bridges = []
        buildings = []
        settlements = []
        schools = []
        hospitals = []
        
        for el in data.get("elements", []):
            tags = el.get("tags", {})
            geom = None
            
            # Construct geometry
            if el["type"] == "node":
                geom = Point(el["lon"], el["lat"])
            elif el["type"] == "way":
                coords = [(pt["lon"], pt["lat"]) for pt in el.get("geometry", [])]
                if len(coords) >= 2:
                    # If it is a closed loop and is a building, make a polygon
                    if coords[0] == coords[-1] and "building" in tags:
                        geom = Polygon(coords)
                    else:
                        geom = LineString(coords)
            
            if not geom:
                continue
                
            props = {"osm_id": el["id"], "name": tags.get("name", "Unknown")}
            
            if "highway" in tags:
                props["type"] = tags["highway"]
                roads.append({"geometry": geom, **props})
                
            if "bridge" in tags:
                bridges.append({"geometry": geom, **props})
                
            if "building" in tags:
                buildings.append({"geometry": geom, **props})
                
            if "place" in tags:
                props["type"] = tags["place"]
                settlements.append({"geometry": geom, **props})
                
            if tags.get("amenity") == "school":
                schools.append({"geometry": geom, **props})
                
            if tags.get("amenity") == "hospital":
                hospitals.append({"geometry": geom, **props})
                
        def make_gdf(features):
            if not features:
                return gpd.GeoDataFrame(columns=["geometry", "osm_id", "name"], crs="EPSG:4326").to_crs(self.crs)
            gdf = gpd.GeoDataFrame(features, crs="EPSG:4326")
            return gdf.to_crs(self.crs)
            
        return {
            "roads": make_gdf(roads),
            "bridges": make_gdf(bridges),
            "buildings": make_gdf(buildings),
            "settlements": make_gdf(settlements),
            "schools": make_gdf(schools),
            "hospitals": make_gdf(hospitals)
        }

    def sample_raster_at_centroids(self, gdf: gpd.GeoDataFrame, raster_path: str, nodata_val=-9999.0):
        """Samples the raster value at the centroid of each geometry."""
        if gdf.empty:
            return []
            
        centroids = gdf.geometry.centroid
        coords = [(pt.x, pt.y) for pt in centroids]
        
        results = []
        with rasterio.open(raster_path) as src:
            for val in src.sample(coords):
                v = val[0]
                if v == src.nodata or np.isnan(v) or v == nodata_val:
                    results.append(None)
                else:
                    results.append(float(v))
        return results

    def run_analysis(self, sim_id: str, scenario_id: str):
        # 1. Fetch and Parse
        osm_data = self.fetch_osm_data()
        layers = self.parse_osm_elements(osm_data)
        
        impacts = {}
        affected_gdfs = {}
        
        # Calculate total flooded area in km2 (using an equal area projection or UTM)
        flooded_area_km2 = self.extent_gdf.geometry.area.sum() / 1e6
        
        print(f"Retrieved from OSM: { {k: len(v) for k, v in layers.items()} }")
        
        for name, gdf in layers.items():
            if gdf.empty:
                impacts[name] = {"count": 0, "affected_length_km": 0.0, "mean_depth_m": None, "max_depth_m": None, "earliest_arrival_time_s": None}
                out_path = os.path.join(self.output_dir, f"{sim_id}_affected_{name}.geojson")
                with open(out_path, 'w') as f:
                    f.write('{"type": "FeatureCollection", "features": []}')
                continue
                
            # 2. Spatial Overlay (Intersection with flood extent)
            # Use 'intersection' to get the actual clipped geometries (e.g. for roads)
            affected = gpd.overlay(gdf, self.extent_gdf, how='intersection')
            
            if affected.empty:
                impacts[name] = {"count": 0, "affected_length_km": 0.0, "mean_depth_m": None, "max_depth_m": None, "earliest_arrival_time_s": None}
                
                out_path = os.path.join(self.output_dir, f"{sim_id}_affected_{name}.geojson")
                with open(out_path, 'w') as f:
                    f.write('{"type": "FeatureCollection", "features": []}')
                continue
                
            # 3. Sample Depth and Arrival Time
            depths = self.sample_raster_at_centroids(affected, self.depth_path)
            arrivals = self.sample_raster_at_centroids(affected, self.arrival_path)
            
            affected["max_depth_m"] = depths
            affected["arrival_time_s"] = arrivals
            
            # 4. Calculate Stats
            valid_depths = [d for d in depths if d is not None and d > 0]
            valid_arrivals = [a for a in arrivals if a is not None and a >= 0]
            
            stats = {
                "count": len(affected),
                "affected_length_km": 0.0,
                "mean_depth_m": float(np.mean(valid_depths)) if valid_depths else None,
                "max_depth_m": float(np.max(valid_depths)) if valid_depths else None,
                "earliest_arrival_time_s": float(np.min(valid_arrivals)) if valid_arrivals else None
            }
            
            if name == "roads":
                stats["affected_length_km"] = affected.geometry.length.sum() / 1000.0
                
            impacts[name] = stats
            affected_gdfs[name] = affected
            
            # Save GeoJSON output
            out_path = os.path.join(self.output_dir, f"{sim_id}_affected_{name}.geojson")
            affected.to_crs("EPSG:4326").to_file(out_path, driver="GeoJSON")
            
        # 5. Build Standardized Output
        summary = {
            "simulation_id": sim_id,
            "scenario_id": scenario_id,
            "flooded_area_km2": float(flooded_area_km2),
            "affected_infrastructure": {
                "roads": impacts["roads"],
                "bridges": impacts["bridges"],
                "buildings": impacts["buildings"],
                "settlements": impacts["settlements"],
                "schools": impacts["schools"],
                "hospitals": impacts["hospitals"]
            },
            "generated_at": datetime.utcnow().isoformat(),
            "provenance": "Overpass API (OSM) spatial intersection with hydrodynamic results.",
            "limitations": [
                "EXTREME HYPOTHETICAL ASSUMPTION: The flood extent represents an engineer-defined stress test, NOT a physically validated real-world event prediction.",
                "SIMULATED ARRIVAL TIMES: Arrival times are mathematical outputs of a baseline solver and are NOT real-time operational warnings.",
                "POTENTIAL AFFECTED FEATURES: Represents features geometrically inside the simulated flood polygon based on open OSM data. Does not claim actual future damage or exact population at risk.",
                "DEPTH SAMPLING: Depths are sampled at the centroid of affected feature geometries, which may not represent the maximum depth across large line/polygon features."
            ]
        }
        
        summary_path = os.path.join(self.output_dir, f"{sim_id}_impact_summary.json")
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=4)
            
        return summary, summary_path
