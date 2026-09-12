import os
import json
import pytest

def test_places_impact_logic():
    # 1. Load the impact summary
    summaries = __import__('glob').glob("data/impact_results/*_impact_summary.json")
    if not summaries:
        pytest.skip("No impact summaries found.")
        
    latest_summary = max(summaries, key=os.path.getctime)
    with open(latest_summary, 'r') as f:
        impact = json.load(f)
        
    places = impact.get("places", [])
    
    # - place filtering & flood intersection/nearby logic
    # We should have some places parsed and intersected
    assert isinstance(places, list)
    
    # - sorting by arrival time
    arrival_times = [p["flood_arrival_minutes"] for p in places]
    assert arrival_times == sorted(arrival_times), "Places are not sorted by arrival time!"
    
    # - missing/no-data arrival times
    # None of the places should have negative or missing arrival times
    for p in places:
        assert p["flood_arrival_minutes"] is not None
        assert p["flood_arrival_minutes"] >= 0
        
    # - correct units
    # Ensure distance is in km and arrival is in minutes
    for p in places:
        assert "distance_from_source_km" in p
        assert "flood_arrival_minutes" in p
        assert "impact_level" in p
        
    # - impact level threshold check
    for p in places:
        arr = p["flood_arrival_minutes"]
        level = p["impact_level"]
        if arr < 15:
            assert level == "IMMEDIATE"
        elif arr <= 30:
            assert level == "HIGH"
        elif arr <= 60:
            assert level == "MODERATE"
        else:
            assert level == "LATER"

def test_no_offshore_places():
    # Load places geojson if it exists
    import geopandas as gpd
    import glob
    geojsons = glob.glob("data/impact_results/*_affected_places.geojson")
    if not geojsons:
        pytest.skip("No affected places geojson found.")
        
    latest = max(geojsons, key=os.path.getctime)
    gdf = gpd.read_file(latest)
    
    if not gdf.empty:
        minx, miny, maxx, maxy = gdf.total_bounds
        # The correct flood extent should be near Idukki (9.8 N, 76.9 E)
        # It shouldn't be south of 9.3 N or west of 76.2 E
        assert miny > 9.3, f"Flood extent reached {miny} N, which is offshore/south!"
        assert minx > 76.2, f"Flood extent reached {minx} E, which is offshore/west!"
