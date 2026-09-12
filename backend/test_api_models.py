from fastapi.testclient import TestClient
from app.main import app
from app.services.simulation_service import SimulationService
from unittest.mock import patch, MagicMock
from app.hydrodynamics.adapter import ModelRegistry

client = TestClient(app)

def test_api_models_list():
    response = client.get("/api/v1/models")
    assert response.status_code == 200
    models = response.json()
    assert len(models) == 3
    
    sph = next(m for m in models if m["id"] == "SPH")
    assert sph["is_available"] is False
    
    bl = next(m for m in models if m["id"] == "BASELINE_DIFFUSIVE_WAVE")
    assert bl["is_available"] is True
    
@patch("app.main.SimulationService.create_simulation")
@patch("app.main._get_simulation_state")
def test_create_simulation_sph_unavailable(mock_get_state, mock_create):
    mock_create.return_value = "sim_sph_123"
    mock_get_state.return_value = {"status": "RUNTIME_UNAVAILABLE"}
    
    # We submit a request for SPH
    payload = {
        "hazard_type": "DAM_BREAK",
        "dam_id": "DAM-123",
        "model_type": "SPH"
    }
    
    response = client.post("/api/v1/simulations", json=payload)
    assert response.status_code == 200
    data = response.json()
    
    # Because SPH is unavailable, it should return RUNTIME_UNAVAILABLE
    assert data["status"] == "RUNTIME_UNAVAILABLE"
    assert data["simulation_id"] == "sim_sph_123"

@patch("app.main.SimulationService.create_simulation")
@patch("app.main._get_simulation_state")
def test_create_simulation_delft_unavailable(mock_get_state, mock_create):
    mock_create.return_value = "sim_delft_123"
    mock_get_state.return_value = {"status": "RUNTIME_UNAVAILABLE"}
    
    payload = {
        "hazard_type": "GLOF",
        "lake_id": "LAKE-123",
        "model_type": "DELFT3D"
    }
    
    response = client.post("/api/v1/simulations", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "RUNTIME_UNAVAILABLE"
