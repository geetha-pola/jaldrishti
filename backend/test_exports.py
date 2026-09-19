import pytest
from fastapi.testclient import TestClient
from app.main import app
import os
import zipfile
import json
import csv

client = TestClient(app)

def test_exports_lifecycle():
    # 1. Start simulation
    dams = client.get("/api/v1/dams").json()
    dam_id = str(dams[0]["id"])
    
    req = {"hazard_type": "DAM_BREAK", "dam_id": dam_id}
    sim_res = client.post("/api/v1/simulations", json=req).json()
    sim_id = sim_res["simulation_id"]
    
    # Wait for completion (since background tasks are sync in TestClient)
    # The simulation should be completed immediately.
    status_res = client.get(f"/api/v1/simulations/{sim_id}").json()
    assert status_res["status"] == "COMPLETED"

    # 2. Get exports metadata
    exp_res = client.get(f"/api/v1/simulations/{sim_id}/exports")
    assert exp_res.status_code == 200
    exports = exp_res.json()["exports"]
    assert len(exports) == 9

    urls = {e["format"]: e["url"] for e in exports}

    # 3. Test GeoJSON
    geojson_res = client.get(urls["geojson"])
    assert geojson_res.status_code == 200
    assert geojson_res.headers["content-type"] == "application/geo+json"
    gj = geojson_res.json()
    assert gj["type"] == "FeatureCollection"

    # 4. Test SHP (ZIP)
    shp_res = client.get(urls["shp"])
    assert shp_res.status_code == 200
    assert shp_res.headers["content-type"] == "application/zip"
    
    # 5. Test KML
    kml_res = client.get(urls["kml"])
    assert kml_res.status_code == 200
    assert b"<kml" in kml_res.content.lower()

    # 6. Test Impact CSV
    csv_res = client.get(urls["csv"])
    assert csv_res.status_code == 200
    csv_text = csv_res.text
    assert "place_name,place_type,distance_km" in csv_text

    # 7. Test Summary JSON
    summary_res = client.get(urls["json"]) # Note: There are two JSONs (impact and summary), let's just get the last one or explicitly URL
    summary_url = [e["url"] for e in exports if e["name"] == "Simulation Summary JSON"][0]
    sum_res = client.get(summary_url)
    assert sum_res.status_code == 200
    summary_data = sum_res.json()
    assert summary_data["model_name"] == "2D Diffusive Wave Baseline Solver"
    
    # 8. Test Package ZIP
    pkg_url = [e["url"] for e in exports if e["name"] == "Complete Result Package"][0]
    pkg_res = client.get(pkg_url)
    assert pkg_res.status_code == 200
    assert pkg_res.headers["content-type"] == "application/zip"

    # 9. Test Invalid ID
    inv_res = client.get("/api/v1/simulations/SIM-INVALID/exports")
    assert inv_res.status_code == 404
