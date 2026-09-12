import os
import json
import pytest
import geopandas as gpd

def test_impact_results_exist():
    import glob
    summaries = glob.glob("data/impact_results/*_impact_summary.json")
    if not summaries:
        pytest.skip("No impact results generated yet.")
        
    latest = max(summaries, key=os.path.getctime)
    with open(latest, 'r') as f:
        data = json.load(f)
        
    # Check structure
    assert "simulation_id" in data
    assert "flooded_area_km2" in data
    assert "affected_infrastructure" in data
    
    infra = data["affected_infrastructure"]
    assert "roads" in infra
    assert "buildings" in infra
    
    # Check scientific honesty
    limitations = data.get("limitations", [])
    assert any("EXTREME HYPOTHETICAL ASSUMPTION" in l for l in limitations)
    assert any("NOT a physically validated real-world event prediction" in l for l in limitations)
    
def test_affected_features_geojson():
    import glob
    geojsons = glob.glob("data/impact_results/*_affected_roads.geojson")
    if not geojsons:
        pytest.skip("No affected roads generated yet.")
        
    latest = max(geojsons, key=os.path.getctime)
    gdf = gpd.read_file(latest)
    
    # It should have crs epsg:4326 for standard geojson outputs
    assert gdf.crs.to_string() == "EPSG:4326"
    
    # Should have sampled raster columns if it's not empty
    if not gdf.empty:
        assert "max_depth_m" in gdf.columns
        assert "arrival_time_s" in gdf.columns
