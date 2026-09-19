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
            # We must not crash, just return an empty feature set for the simulation
            pass
            
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
          way["place"]({bbox});
          way["landuse"="residential"]({bbox});
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
        places = []
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
                places.append({"geometry": geom, **props})
            elif tags.get("landuse") == "residential":
                props["type"] = "residential"
                places.append({"geometry": geom, **props})
                
            if tags.get("amenity") == "school":
                schools.append({"geometry": geom, **props})
                
            if tags.get("amenity") == "hospital":
                hospitals.append({"geometry": geom, **props})
                
        def make_gdf(features):
            if not features:
                return gpd.GeoDataFrame(columns=["geometry", "osm_id", "name", "type"], crs="EPSG:4326").to_crs(self.crs)
            gdf = gpd.GeoDataFrame(features, crs="EPSG:4326")
            if "type" not in gdf.columns:
                gdf["type"] = "Unknown"
            return gdf.to_crs(self.crs)
            
        return {
            "roads": make_gdf(roads),
            "bridges": make_gdf(bridges),
            "buildings": make_gdf(buildings),
            "places": make_gdf(places),
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

    def get_impact_level(self, arrival_minutes: float) -> str:
        if arrival_minutes < 15:
            return "IMMEDIATE"
        elif arrival_minutes <= 30:
            return "HIGH"
        elif arrival_minutes <= 60:
            return "MODERATE"
        else:
            return "LATER"

    def run_analysis(self, sim_id: str, scenario_id: str):
        # 1. Fetch and Parse
        osm_data = self.fetch_osm_data()
        layers = self.parse_osm_elements(osm_data)
        
        impacts = {}
        affected_gdfs = {}
        
        # Calculate total flooded area in km2 (using an equal area projection or UTM)
        flooded_area_km2 = self.extent_gdf.geometry.area.sum() / 1e6
        
        print(f"Retrieved from OSM: { {k: len(v) for k, v in layers.items()} }")
        
        # Need source location for distance calculations
        with open('data/domain/idukki_scenario.json', 'r') as f:
            scenario_json = json.load(f)
        dam_lon, dam_lat = scenario_json['source_location']['lon'], scenario_json['source_location']['lat']
        
        # Transform dam location to match CRS for Euclidean distance (in meters)
        from pyproj import Transformer
        t = Transformer.from_crs('EPSG:4326', self.crs, always_xy=True)
        dam_x, dam_y = t.transform(dam_lon, dam_lat)
        dam_pt = Point(dam_x, dam_y)
        
        for name, gdf in layers.items():
            if gdf.empty:
                impacts[name] = {"count": 0, "affected_length_km": 0.0, "mean_depth_m": None, "max_depth_m": None, "earliest_arrival_time_s": None}
                out_path = os.path.join(self.output_dir, f"{sim_id}_affected_{name}.geojson")
                with open(out_path, 'w') as f:
                    f.write('{"type": "FeatureCollection", "features": []}')
                continue
                
            # 2. Spatial Overlay (Intersection with flood extent)
            # Use 'clip' instead of 'overlay' to handle mixed geometries like points and lines in the same gdf
            affected = gpd.clip(gdf, self.extent_gdf)
            
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
            
            # Distance from dam
            affected["distance_from_source_km"] = affected.geometry.centroid.distance(dam_pt) / 1000.0
            
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
            
        # Compile places for the primary output
        places_list = []
        if not affected_gdfs.get("places", gpd.GeoDataFrame()).empty:
            places_gdf = affected_gdfs["places"]
            # Filter to named places only
            named_places = places_gdf[places_gdf["name"] != "Unknown"].copy()
            
            for _, row in named_places.iterrows():
                arr = row.get("arrival_time_s")
                depth = row.get("max_depth_m")
                
                if arr is None or arr < 0:
                    continue
                    
                arr_min = float(arr) / 60.0
                
                places_list.append({
                    "name": row.get("name"),
                    "type": row.get("type", "Unknown"),
                    "distance_from_source_km": float(row.get("distance_from_source_km", 0.0)),
                    "flood_arrival_minutes": arr_min,
                    "max_depth_m": float(depth) if depth else None,
                    "impact_level": self.get_impact_level(arr_min)
                })
                
            # Sort by arrival time
            places_list.sort(key=lambda x: x["flood_arrival_minutes"])
            
        # 5. Build Standardized Output
        summary = {
            "simulation_id": sim_id,
            "scenario_id": scenario_id,
            "flooded_area_km2": float(flooded_area_km2),
            "places": places_list,
            "affected_infrastructure": {
                "roads": impacts.get("roads"),
                "bridges": impacts.get("bridges"),
                "buildings": impacts.get("buildings"),
                "schools": impacts.get("schools"),
                "hospitals": impacts.get("hospitals")
            },
            "generated_at": datetime.utcnow().isoformat(),
            "provenance": "Overpass API (OSM) spatial intersection with hydrodynamic results.",
            "limitations": [
                "BASELINE SOLVER: This uses a simplified 2D Diffusive Wave approximation, not full SWE.",
                "NUMERICAL VELOCITY CAP: The maximum velocity is artificially capped at 30 m/s for numerical stability, NOT as a scientifically validated physical Froude limit.",
                "EXTREME HYPOTHETICAL ASSUMPTION: The flood extent represents an engineer-defined stress test, NOT a physically validated real-world event prediction.",
                "MODEL-ESTIMATED ARRIVAL TIMES: Arrival times are mathematical outputs of a baseline solver and are NOT real-time operational warnings. Never claim the flood 'WILL' reach a place.",
                "POTENTIAL AFFECTED FEATURES: Represents features geometrically inside the simulated flood polygon based on open OSM data. Does not claim actual future damage or exact population at risk.",
                "DEPTH SAMPLING: Depths are sampled at the centroid of affected feature geometries, which may not represent the maximum depth across large line/polygon features."
            ]
        }
        
        summary_path = os.path.join(self.output_dir, f"{sim_id}_impact_summary.json")
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=4)
            
        return summary, summary_path
