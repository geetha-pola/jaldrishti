import pytest
from app.scenarios.models import ParameterValue, ProvenanceStatus, DamBreakParameters
from app.scenarios.breach import BreachHydrographGenerator

def test_negative_physical_parameters():
    """Test that physical parameters cannot be negative."""
    with pytest.raises(ValueError, match="Physical parameter cannot be negative"):
        param = ParameterValue(value=-10.0, unit="m", provenance=ProvenanceStatus.ASSUMED)
        DamBreakParameters(
            dam_height=param,
            initial_water_level=param,
            initial_storage_volume=param,
            breach_width=param,
            breach_depth=param,
            breach_formation_time=param
        )

def test_hydrograph_conservation_of_volume():
    """Test that the generated hydrograph integrates back to the initial volume."""
    vol = 1_000_000 # 1 million m^3
    q_peak = 5000.0 # 5000 m^3/s
    t_peak_hr = 0.1 # 6 minutes
    
    hydrograph = BreachHydrographGenerator.generate_triangular_hydrograph(vol, q_peak, t_peak_hr)
    
    assert len(hydrograph) == 3
    assert hydrograph[0].discharge_cms == 0.0
    assert hydrograph[1].discharge_cms == q_peak
    assert hydrograph[2].discharge_cms == 0.0
    
    # Calculate area of triangle: 0.5 * base * height
    base_seconds = hydrograph[2].time_seconds
    integrated_volume = 0.5 * base_seconds * q_peak
    
    assert pytest.approx(integrated_volume) == vol

def test_froehlich_equations():
    """Test the empirical Froehlich 1995 equations."""
    vol = 1996.3 * 1_000_000
    head = 168.91
    
    q_peak, t_f = BreachHydrographGenerator.calculate_froehlich_1995(vol, head)
    
    # Froehlich peak = 0.607 * (1996300000^0.295) * (168.91^1.24)
    expected_peak = 0.607 * (vol ** 0.295) * (head ** 1.24)
    assert pytest.approx(q_peak) == expected_peak
    assert t_f > 0

def test_provenance_enum():
    """Test provenance status explicitly."""
    p = ParameterValue(value=10, unit="m", provenance="OBSERVED")
    assert p.provenance == ProvenanceStatus.OBSERVED
    
    with pytest.raises(ValueError):
        ParameterValue(value=10, unit="m", provenance="GUESSED")
