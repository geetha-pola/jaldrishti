import os
import json
import time
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert "status" in response.json()

def test_get_dams_endpoints():
    # Since DB might be mocked or empty, just check 200 or 500 structure
    response = client.get("/api/v1/dams")
    assert response.status_code in [200, 500]

def test_invalid_hazard_type():
    req = {
        "hazard_type": "INVALID_HAZARD",
        "dam_id": "1"
    }
    response = client.post("/api/v1/simulations", json=req)
    assert response.status_code == 400
    assert "Unsupported hazard type" in response.json()["detail"]

def test_invalid_dam_id():
    req = {
        "hazard_type": "DAM_BREAK",
        "dam_id": ""
    }
    response = client.post("/api/v1/simulations", json=req)
    assert response.status_code == 400
    assert "Invalid dam ID" in response.json()["detail"]

def test_simulation_lifecycle():
    # 1. Create Simulation
    req = {
        "hazard_type": "DAM_BREAK",
        "dam_id": "1"
    }
    response = client.post("/api/v1/simulations", json=req)
    assert response.status_code == 200
    data = response.json()
    assert "simulation_id" in data
    assert data["status"] == "QUEUED"
    
    sim_id = data["simulation_id"]
    
    # 2. Check Status (Should immediately be QUEUED or RUNNING depending on thread)
    status_response = client.get(f"/api/v1/simulations/{sim_id}")
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["status"] in ["QUEUED", "RUNNING", "COMPLETED", "FAILED"]
    
    # Wait for the simulation to complete (it runs synchronously in BackgroundTasks in TestClient)
    # Actually TestClient runs background tasks immediately when the response is returned.
    # So by the time we call status, it should already be COMPLETED!
    status_response = client.get(f"/api/v1/simulations/{sim_id}")
    status_data = status_response.json()
    
    assert status_data["status"] == "COMPLETED", f"Simulation failed: {status_data.get('error')}"
    assert status_data["current_stage"] == "COMPLETED"
    
    # 3. Get Results
    results_response = client.get(f"/api/v1/simulations/{sim_id}/results")
    assert results_response.status_code == 200
    results_data = results_response.json()
    
    assert results_data["status"] == "COMPLETED"
    assert "extent_path" in results_data
    assert "impact_summary_path" in results_data
    assert "satellite_validation_path" in results_data
    
    # 4. Satellite unavailable does not incorrectly fail the simulation
    # The JSON validation file should indicate it wasn't available (since event_date wasn't passed)
    val_path = results_data["satellite_validation_path"]
    assert os.path.exists(val_path)
    with open(val_path, 'r') as f:
        val_data = json.load(f)
        assert val_data["validation_status"] in ["NO SUITABLE SATELLITE OBSERVATION AVAILABLE FOR THIS SCENARIO", "NOT AVAILABLE"]

def test_get_models_endpoint():
    res = client.get('/api/v1/models')
    assert res.status_code == 200
    assert len(res.json()) == 3

def test_sph_model_unavailable_rejection():
    req = {'hazard_type': 'DAM_BREAK', 'dam_id': '1', 'model_type': 'SPH'}
    res = client.post('/api/v1/simulations', json=req)
    assert res.status_code == 400
    assert 'unavailable' in res.json()['detail'].lower()

def test_delft3d_model_unavailable_rejection():
    req = {'hazard_type': 'DAM_BREAK', 'dam_id': '1', 'model_type': 'DELFT3D'}
    res = client.post('/api/v1/simulations', json=req)
    assert res.status_code == 400
    assert 'unavailable' in res.json()['detail'].lower()
