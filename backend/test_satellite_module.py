import os
import json
import pytest
import geopandas as gpd
from shapely.geometry import Polygon
from app.satellite.validation import SatelliteValidator

def test_metrics_calculation():
    validator = SatelliteValidator()
    
    # Create dummy geodataframes
    poly1 = Polygon([(0, 0), (0, 1000), (1000, 1000), (1000, 0)]) # 1 sq km
    poly2 = Polygon([(500, 0), (500, 1000), (1500, 1000), (1500, 0)]) # 1 sq km
    
    # Using a projected CRS where 1 unit = 1 meter
    gdf1 = gpd.GeoDataFrame(geometry=[poly1], crs="EPSG:32643")
    gdf2 = gpd.GeoDataFrame(geometry=[poly2], crs="EPSG:32643")
    
    metrics = validator.calculate_metrics(gdf1, gdf2)
    
    # Intersection is 500x1000 = 0.5 sq km
    assert abs(metrics["intersection_area_km2"] - 0.5) < 0.01
    
    # Union is 1500x1000 = 1.5 sq km
    # IoU = 0.5 / 1.5 = 33.33%
    assert abs(metrics["iou"] - 33.33) < 0.1
    
    # Precision = 0.5 / 1.0 = 50%
    assert abs(metrics["precision"] - 50.0) < 0.1
    
    # Recall = 0.5 / 1.0 = 50%
    assert abs(metrics["recall"] - 50.0) < 0.1

def test_crs_consistency_handling():
    validator = SatelliteValidator()
    
    # poly1 in UTM
    poly1 = Polygon([(0, 0), (0, 1000), (1000, 1000), (1000, 0)])
    gdf1 = gpd.GeoDataFrame(geometry=[poly1], crs="EPSG:32643")
    
    # poly2 same shape, but let's say it was in 4326 and converted back
    poly2 = Polygon([(0, 0), (0, 1000), (1000, 1000), (1000, 0)])
    gdf2 = gpd.GeoDataFrame(geometry=[poly2], crs="EPSG:3857")
    
    # The calculate_metrics should handle the CRS projection internally without crashing
    metrics = validator.calculate_metrics(gdf1, gdf2)
    assert "iou" in metrics

def test_empty_geometries():
    validator = SatelliteValidator()
    gdf1 = gpd.GeoDataFrame(geometry=[], crs="EPSG:32643")
    gdf2 = gpd.GeoDataFrame(geometry=[], crs="EPSG:32643")
    
    metrics = validator.calculate_metrics(gdf1, gdf2)
    assert metrics["iou"] == 0.0
    assert metrics["modeled_area_km2"] == 0.0

def test_hypothetical_scenario_validation_status():
    import glob
    geojsons = glob.glob("data/hydro_results/*_extent.geojson")
    if not geojsons:
        pytest.skip("No flood extents found.")
        
    latest_extent = max(geojsons, key=os.path.getctime)
    sim_id = "TEST-SIM"
    
    validator = SatelliteValidator()
    summary = validator.validate_simulation(sim_id, latest_extent, event_date=None)
    
    # Since event_date is None, it should correctly report no suitable observation
    assert summary["validation_status"] == "NO SUITABLE SATELLITE OBSERVATION AVAILABLE FOR THIS SCENARIO"
    assert "limitations" in summary
    assert any("HYPOTHETICAL EVENT" in l for l in summary["limitations"])
    assert any("MODEL SCENARIO STATUS" in l for l in summary["limitations"])
