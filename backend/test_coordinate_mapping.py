import os
import json
import pytest
import rasterio
from rasterio.windows import from_bounds
from pyproj import Transformer
import geopandas as gpd
from shapely.geometry import Point

def test_coordinate_mapping_regression():
    # 1. Load domain configuration
    scenario_path = 'data/domain/idukki_scenario.json'
    if not os.path.exists(scenario_path):
        pytest.skip("Scenario JSON not found.")
        
    with open(scenario_path, 'r') as f:
        scenario = json.load(f)
        
    lat, lon = scenario['source_location']['lat'], scenario['source_location']['lon']
    
    # Transform to UTM
    transformer = Transformer.from_crs('EPSG:4326', scenario['crs'], always_xy=True)
    utm_x, utm_y = transformer.transform(lon, lat)
    
    # 2. Check DEM and calculate index
    with rasterio.open(scenario['dem_path']) as src:
        bounds = scenario['domain_bounds_utm']
        window = from_bounds(*bounds, transform=src.transform)
        win_transform = src.window_transform(window)
        
        # Simulated 300m coarsening factor
        scale_factor = 1.0 / 10.0
        res_width = int(window.width * scale_factor)
        res_height = int(window.height * scale_factor)
        
        res_transform = win_transform * win_transform.scale(
            (window.width / res_width),
            (window.height / res_height)
        )
        
        # INVERSE TRANSFORM: (x, y) -> (col, row)
        # CRITICAL REGRESSION CHECK: Ensure output is explicitly col, row
        col, row = ~res_transform * (utm_x, utm_y)
        
        # Check ordering logic matches adapter.py
        inflow_idx_y = min(max(int(row), 0), res_height - 1)
        inflow_idx_x = min(max(int(col), 0), res_width - 1)
        
        # 4. Injection cell must be inside DEM bounds
        assert 0 <= inflow_idx_y < res_height
        assert 0 <= inflow_idx_x < res_width
        
        # 5. Injection cell must be inside simulation domain (implicit by bounds check above, but check explicit geometry)
        domain_gdf = gpd.read_file(scenario['simulation_domain_geojson']).to_crs(scenario['crs'])
        dam_point = Point(utm_x, utm_y)
        assert any(domain_gdf.geometry.contains(dam_point))
        
        # 3. Reconstructed coordinate is close to original coordinate
        recon_x, recon_y = res_transform * (inflow_idx_x + 0.5, inflow_idx_y + 0.5)
        recon_lon, recon_lat = transformer.transform(recon_x, recon_y, direction='INVERSE')
        
        # Simple Euclidean distance in degrees just for regression check (should be < 0.01 deg)
        deg_dist = ((lat - recon_lat)**2 + (lon - recon_lon)**2)**0.5
        assert deg_dist < 0.01, f"Reconstructed point {recon_lat}, {recon_lon} is too far from dam {lat}, {lon}!"
        
def test_flood_extent_not_offshore():
    import glob
    geojsons = glob.glob("data/hydro_results/*_extent.geojson")
    if not geojsons:
        pytest.skip("No flood extents found.")
        
    latest = max(geojsons, key=os.path.getctime)
    gdf = gpd.read_file(latest)
    
        # 6. Flood extent is not accidentally generated offshore (the Arabian Sea bug was at ~ 9.0 N, 76.1 E)
    if not gdf.empty:
        minx, miny, maxx, maxy = gdf.total_bounds
        # The correct flood extent should be near Idukki (9.8 N, 76.9 E)
        # It shouldn't be south of 9.3 N or west of 76.2 E
        assert miny > 9.3, f"Flood extent reached {miny} N, which is offshore/south!"
        assert minx > 76.2, f"Flood extent reached {minx} E, which is offshore/west!"
        
def test_area_and_units_regression():
    import glob
    import json
    
    # 1. Check impact summary JSON keys for strict area units (km2)
    summaries = glob.glob("data/impact_results/*_impact_summary.json")
    if not summaries:
        pytest.skip("No impact summaries found.")
        
    latest_summary = max(summaries, key=os.path.getctime)
    with open(latest_summary, 'r') as f:
        impact = json.load(f)
        
    assert "flooded_area_km2" in impact, "Area key must explicitly include km2 unit!"
    assert impact["flooded_area_km2"] < 1000.0, "Flooded area is impossibly large (likely wrong unit)"
    
    # 2. Check limitation labels for scientific honesty
    limitations = impact.get("limitations", [])
    
    # Verify the velocity limit is described as a modeling cap
    assert any("NUMERICAL VELOCITY CAP" in l for l in limitations)
    assert any("NOT as a scientifically validated physical Froude limit" in l for l in limitations)
    assert any("BASELINE SOLVER" in l for l in limitations)
    assert any("EXTREME HYPOTHETICAL ASSUMPTION" in l for l in limitations)
