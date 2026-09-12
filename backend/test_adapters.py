import pytest
import os
from unittest.mock import MagicMock
from app.hydrodynamics.adapter import ModelRegistry

@pytest.fixture
def dummy_scenario():
    scenario = MagicMock()
    scenario.scenario_id = "TEST_001"
    scenario.simulation_duration_hours.value = 1.0
    scenario.inflow_hydrograph = []
    return scenario

def test_sph_adapter_unavailable_behavior(dummy_scenario, tmp_path):
    sph = ModelRegistry.get_adapter("SPH")
    assert not sph.is_available
    
    # Input generation should succeed without error
    out_dir = str(tmp_path)
    sph.prepare_input(dummy_scenario, out_dir)
    assert os.path.exists(os.path.join(out_dir, "TEST_001_sph_case.xml"))
    
    # Run should raise explicitly (no silent fallback)
    with pytest.raises(RuntimeError, match="unavailable"):
        sph.run(dummy_scenario, out_dir)

def test_delft3d_adapter_unavailable_behavior(dummy_scenario, tmp_path):
    d3d = ModelRegistry.get_adapter("DELFT3D")
    assert not d3d.is_available
    
    # Input generation should succeed without error
    out_dir = str(tmp_path)
    d3d.prepare_input(dummy_scenario, out_dir)
    assert os.path.exists(os.path.join(out_dir, "TEST_001.mdu"))
    assert os.path.exists(os.path.join(out_dir, "TEST_001.bc"))
    
    # Run should raise explicitly (no silent fallback)
    with pytest.raises(RuntimeError, match="unavailable"):
        d3d.run(dummy_scenario, out_dir)
