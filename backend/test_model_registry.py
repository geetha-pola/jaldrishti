import pytest
from app.hydrodynamics.adapter import ModelRegistry

def test_model_registry_list():
    models = ModelRegistry.list_models()
    assert len(models) == 3
    
    ids = [m["id"] for m in models]
    assert "BASELINE_DIFFUSIVE_WAVE" in ids
    assert "SPH" in ids
    assert "DELFT3D" in ids

def test_model_availability():
    bl = ModelRegistry.get_adapter("BASELINE_DIFFUSIVE_WAVE")
    assert bl.is_available is True
    
    sph = ModelRegistry.get_adapter("SPH")
    assert sph.is_available is False
    
    delft = ModelRegistry.get_adapter("DELFT3D")
    assert delft.is_available is False

def test_invalid_model_request():
    with pytest.raises(ValueError, match="Unknown model type: INVALID"):
        ModelRegistry.get_adapter("INVALID")
