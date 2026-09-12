import uuid
import datetime
from typing import Dict, Any, Tuple
from .models import (
    StandardizedModelInput, ScenarioType, ProvenanceStatus, 
    ParameterValue, DamBreakParameters, HydrographPoint
)
from .breach import BreachHydrographGenerator

class ScenarioGenerator:
    """
    Generalized scenario-generation system converting hazard data into a standardized hydrodynamic input.
    """
    
    def __init__(self):
        pass
        
    def generate_dam_break_scenario(
        self,
        dam_name: str,
        lat: float,
        lon: float,
        dem_path: str,
        crs: str,
        domain_geojson: str,
        domain_bounds_utm: Tuple[float, float, float, float],
        initial_water_level_m: ParameterValue,
        initial_storage_mcm: ParameterValue,
        dam_height_m: ParameterValue,
        # Default scenario simulation configs
        sim_duration_hours: float = 24.0,
        timestep_seconds: float = 1.0,
        manning_n: float = 0.04
    ) -> StandardizedModelInput:
        """
        Creates a standardized DAM BREAK scenario.
        For Idukki (Concrete Arch), we will demonstrate a hypothetical instantaneous failure,
        or fall back to Froehlich if the user prefers. Here we calculate an assumed peak discharge
        based on total structural collapse for demonstration, or use Froehlich for generalization.
        """
        
        # Volume in cubic meters
        volume_m3 = initial_storage_mcm.value * 1_000_000
        
        # Head in meters (assuming reservoir is full to the initial water level, 
        # and breach depth is the full dam height for a catastrophic failure)
        head_m = dam_height_m.value
        
        # Because Idukki is a concrete arch dam, Froehlich 1995 earthen dam equations are physically inappropriate.
        # However, to maintain a generalized pipeline, we will calculate Froehlich, but explicitly mark
        # the parameters as ENGINEER_DEFINED or ASSUMED with clear limitations.
        
        q_peak, t_failure_hr = BreachHydrographGenerator.calculate_froehlich_1995(volume_m3, head_m)
        
        # Concrete arch dams fail almost instantaneously. 
        # We override Froehlich's slow earthen breach time with an ASSUMED instantaneous failure (e.g. 0.1 hours).
        assumed_t_failure_hr = 0.1 
        
        hydrograph = BreachHydrographGenerator.generate_triangular_hydrograph(
            volume_m3=volume_m3,
            peak_discharge_cms=q_peak,
            time_to_peak_hours=assumed_t_failure_hr
        )
        
        breach_params = DamBreakParameters(
            dam_height=dam_height_m,
            initial_water_level=initial_water_level_m,
            initial_storage_volume=ParameterValue(
                value=volume_m3, 
                unit="m^3", 
                provenance=initial_storage_mcm.provenance,
                reference=initial_storage_mcm.reference
            ),
            breach_width=ParameterValue(
                value=200.0, # Assumed full width of gorge
                unit="m",
                provenance=ProvenanceStatus.ASSUMED,
                assumptions="Assumed total structural collapse of concrete arch."
            ),
            breach_depth=ParameterValue(
                value=head_m,
                unit="m",
                provenance=ProvenanceStatus.ASSUMED,
                assumptions="Assumed breach down to foundation."
            ),
            breach_formation_time=ParameterValue(
                value=assumed_t_failure_hr,
                unit="hours",
                provenance=ProvenanceStatus.ENGINEER_DEFINED,
                assumptions="Instantaneous collapse assumed for concrete arch dam, overriding Froehlich 1995."
            )
        )
        
        limitations = [
            "HYPOTHETICAL SCENARIO: This does not represent an actual or predicted event.",
            "BREACH EQUATION: Peak discharge calculated via Froehlich (1995), which is designed for earthen dams, not concrete arch dams. Results are approximate.",
            "ROUTING: The outflow hydrograph assumes a simplified triangular distribution.",
            "HYDRODYNAMICS: This input must be routed by a 2D Shallow Water Equation solver (SPH/Delft3D) to determine actual flood extents."
        ]
        
        scenario_id = f"SCEN-{dam_name[:3].upper()}-{uuid.uuid4().hex[:6]}"
        
        scenario_name = "Extreme Hypothetical Stress-Test Scenario"
        
        return StandardizedModelInput(
            scenario_id=scenario_id,
            scenario_name=scenario_name,
            hazard_type="DAM_BREAK",
            scenario_type=ScenarioType.HYPOTHETICAL,
            source_location={"lat": lat, "lon": lon},
            dem_path=dem_path,
            crs=crs,
            simulation_domain_geojson=domain_geojson,
            domain_bounds_utm=domain_bounds_utm,
            breach_parameters=breach_params,
            inflow_hydrograph=hydrograph,
            simulation_duration_hours=ParameterValue(
                value=sim_duration_hours, unit="hours", provenance=ProvenanceStatus.ENGINEER_DEFINED
            ),
            timestep_seconds=ParameterValue(
                value=timestep_seconds, unit="seconds", provenance=ProvenanceStatus.ENGINEER_DEFINED
            ),
            manning_roughness=ParameterValue(
                value=manning_n, unit="n", provenance=ProvenanceStatus.ASSUMED, assumptions="Uniform global roughness assumed."
            ),
            generated_at=datetime.datetime.utcnow().isoformat(),
            limitations=limitations
        )
