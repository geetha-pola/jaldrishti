import math
from datetime import datetime
from uuid import uuid4
from typing import Dict, Any, List

from app.scenarios.models import (
    StandardizedModelInput,
    ScenarioType,
    ParameterValue,
    ProvenanceStatus,
    DamBreakParameters,
    HydrographPoint
)

class GLOFScenarioGenerator:
    """
    Generates a StandardizedModelInput for a Glacial Lake Outburst Flood (GLOF) scenario.
    """
    
    @staticmethod
    def generate_scenario(lake: Dict[str, Any], dem_path: str, bounds_utm: tuple, crs: str) -> StandardizedModelInput:
        """
        Creates a stress-test GLOF scenario from lake parameters.
        """
        scenario_id = f"GLOF-SCENARIO-{uuid4().hex[:6]}"
        
        # 1. Estimate Outburst Volume
        # We assume 100% of the estimated volume is released for this extreme stress test.
        volume_m3 = lake.get("estimated_volume_m3", 0.0)
        if volume_m3 <= 0:
            raise ValueError("Lake must have a positive estimated_volume_m3 to simulate a GLOF.")
            
        depth_m = lake.get("estimated_depth_m", 30.0)
        
        # 2. Estimate Peak Discharge (Qp)
        # Using empirical relationship for moraine-dammed lakes: 
        # Costa (1988): Qp = 0.00013 * V^1.04 (for V in m3)
        # Note: This is an empirical envelope curve and not a universal physical law.
        q_peak = 0.00013 * math.pow(volume_m3, 1.04)
        
        # 3. Create idealized triangular hydrograph
        # Mass conservation: V = 0.5 * Qp * T_base  => T_base = 2V / Qp
        t_base_seconds = 2.0 * volume_m3 / q_peak
        
        # We assume breach forms and reaches peak quickly (e.g. at 20% of the base time)
        t_peak = 0.2 * t_base_seconds
        
        hydrograph = [
            HydrographPoint(time_seconds=0.0, discharge_cms=0.0),
            HydrographPoint(time_seconds=t_peak, discharge_cms=q_peak),
            HydrographPoint(time_seconds=t_base_seconds, discharge_cms=0.0),
            HydrographPoint(time_seconds=t_base_seconds * 1.5, discharge_cms=0.0) # pad tail
        ]
        
        # Convert bounds to geojson polygon for domain
        w, s, e, n = bounds_utm
        import json
        from shapely.geometry import box
        import geopandas as gpd
        gdf = gpd.GeoDataFrame({'geometry': [box(w, s, e, n)]}, crs=crs)
        geojson_domain = gdf.to_crs("EPSG:4326").to_json()
        
        sim_duration_hrs = math.ceil(t_base_seconds / 3600.0) + 1.0
        
        return StandardizedModelInput(
            scenario_id=scenario_id,
            scenario_name="Extreme Hypothetical GLOF Stress-Test",
            hazard_type="GLOF",
            scenario_type=ScenarioType.HYPOTHETICAL,
            source_location={"lat": lake["latitude"], "lon": lake["longitude"]},
            dem_path=dem_path,
            crs=crs,
            simulation_domain_geojson=geojson_domain,
            domain_bounds_utm=bounds_utm,
            breach_parameters=DamBreakParameters(
                dam_height=ParameterValue(value=depth_m, unit="m", provenance=ProvenanceStatus.ESTIMATED, assumptions="Lake depth acts as effective moraine dam height"),
                initial_water_level=ParameterValue(value=depth_m, unit="m", provenance=ProvenanceStatus.ESTIMATED),
                initial_storage_volume=ParameterValue(value=volume_m3, unit="m3", provenance=ProvenanceStatus.ESTIMATED),
                breach_width=ParameterValue(value=0.0, unit="m", provenance=ProvenanceStatus.ASSUMED, assumptions="Breach geometry not explicitly modeled in inflow, handled via empirical hydrograph"),
                breach_depth=ParameterValue(value=0.0, unit="m", provenance=ProvenanceStatus.ASSUMED),
                breach_formation_time=ParameterValue(value=t_peak / 3600.0, unit="hr", provenance=ProvenanceStatus.ENGINEER_DEFINED, assumptions="Triangular hydrograph peak time")
            ),
            inflow_hydrograph=hydrograph,
            simulation_duration_hours=ParameterValue(value=sim_duration_hrs, unit="hr", provenance=ProvenanceStatus.ENGINEER_DEFINED),
            timestep_seconds=ParameterValue(value=0.5, unit="s", provenance=ProvenanceStatus.ENGINEER_DEFINED),
            manning_roughness=ParameterValue(value=0.04, unit="n", provenance=ProvenanceStatus.ASSUMED, assumptions="Typical mountain river valley roughness"),
            generated_at=datetime.utcnow().isoformat(),
            limitations=[
                "EMPIRICAL PEAK: Qp estimated via Costa (1988) for moraine-dammed lakes. This is an empirical estimate, not a universal physical law, and may differ substantially from site-specific behavior.",
                "100% RELEASE: Assumes total instantaneous volume release, representing an absolute worst-case stress test, NOT a specific prediction.",
                "TRIANGULAR HYDROGRAPH: Uses simplified geometric hydrograph rather than physically modeled breach widening.",
                "JALDRISHTI does not predict exactly when a GLOF will occur. It simulates the downstream consequences of a defined or estimated outburst scenario."
            ]
        )
