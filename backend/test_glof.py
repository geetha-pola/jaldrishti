import pytest
from app.main import app
from fastapi.testclient import TestClient
from app.schemas import GlacialLakeResponse, SimulationRequest
from app.scenarios.glof_generator import GLOFScenarioGenerator
from app.scenarios.models import ProvenanceStatus
import math

client = TestClient(app)

def test_glacial_lake_schema():
    # Valid
    data = {
        "id": "L-001",
        "name": "Test Lake",
        "latitude": 27.5,
        "longitude": 88.5,
        "elevation_m": 5000.0,
        "area_sq_m": 1e6,
        "estimated_depth_m": 40.0,
        "estimated_volume_m3": 4e7,
        "downstream_river": "Test River",
        "provenance": "ESTIMATED",
        "geojson": {}
    }
    lake = GlacialLakeResponse(**data)
    assert lake.name == "Test Lake"
    assert lake.provenance == "ESTIMATED"

def test_lake_api_list():
    res = client.get("/api/v1/lakes")
    assert res.status_code == 200
    lakes = res.json()
    assert len(lakes) > 0
    assert "South Lhonak Lake" in lakes[0]["name"]

def test_lake_api_get():
    res = client.get("/api/v1/lakes/LAKE-001")
    assert res.status_code == 200
    lake = res.json()
    assert lake["id"] == "LAKE-001"
    assert lake["estimated_volume_m3"] == 8.35e7

def test_invalid_lake():
    res = client.get("/api/v1/lakes/INVALID_ID")
    assert res.status_code == 404

def test_glof_hydrograph_and_conservation():
    lake = {
        "id": "L-1",
        "name": "Test Lake",
        "latitude": 27.0,
        "longitude": 88.0,
        "estimated_volume_m3": 8.35e7,
        "estimated_depth_m": 50.0
    }
    bounds = (100, 200, 300, 400)
    crs = "EPSG:32645"
    
    scenario = GLOFScenarioGenerator.generate_scenario(lake, "dummy.tif", bounds, crs)
    
    assert scenario.hazard_type == "GLOF"
    assert scenario.breach_parameters.initial_storage_volume.value == 8.35e7
    assert scenario.breach_parameters.initial_storage_volume.provenance == ProvenanceStatus.ESTIMATED
    
    hydrograph = scenario.inflow_hydrograph
    assert len(hydrograph) == 4
    
    # Check empirical peak (Qp = 0.00013 * V^1.04)
    expected_peak = 0.00013 * math.pow(8.35e7, 1.04)
    assert math.isclose(hydrograph[1].discharge_cms, expected_peak, rel_tol=1e-3)
    
    # Check volume conservation (Area of triangle)
    t_peak = hydrograph[1].time_seconds
    q_peak = hydrograph[1].discharge_cms
    t_base = hydrograph[2].time_seconds
    
    area = 0.5 * t_base * q_peak
    assert math.isclose(area, 8.35e7, rel_tol=1e-3)

def test_invalid_glof_lake_volume():
    lake = {
        "id": "L-1",
        "name": "Test Lake",
        "latitude": 27.0,
        "longitude": 88.0,
        "estimated_volume_m3": 0.0,  # Invalid volume
    }
    with pytest.raises(ValueError, match="positive estimated_volume_m3"):
        GLOFScenarioGenerator.generate_scenario(lake, "dummy.tif", (0,0,1,1), "EPSG:4326")

def test_glof_simulation_orchestration():
    # 1. Trigger Simulation
    req = {
        "hazard_type": "GLOF",
        "lake_id": "LAKE-001",
        "model_type": "BASELINE_DIFFUSIVE_WAVE"
    }
    res = client.post("/api/v1/simulations", json=req)
    assert res.status_code == 200
    sim_id = res.json()["simulation_id"]
    
    # The background task will run (TestClient runs it synchronously)
    # 2. Check Status
    res = client.get(f"/api/v1/simulations/{sim_id}")
    assert res.status_code == 200
    status = res.json()
    assert status["status"] == "COMPLETED"
    assert status["actual_model"] == "BASELINE_DIFFUSIVE_WAVE"
    
    # 3. Check Results
    res = client.get(f"/api/v1/simulations/{sim_id}/results")
    assert res.status_code == 200
    results = res.json()
    
    assert results["extent_path"] is not None
    assert results["impact_summary_path"] is not None
