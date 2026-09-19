import json
import logging
from app.scenarios import (
    ScenarioGenerator, 
    ParameterValue, 
    ProvenanceStatus,
    ScenarioType
)

logging.basicConfig(level=logging.INFO)

def test_idukki_scenario():
    print("--- GENERATING IDUKKI DAM HYPOTHETICAL SCENARIO ---")
    
    # These values come from our Database/CWC Importer (Milestone 1 & 2)
    # Idukki Dam verified facts:
    # Height: 168.91 m
    # Storage: 1996.3 MCM
    
    generator = ScenarioGenerator()
    
    scenario = generator.generate_dam_break_scenario(
        dam_name="Idukki",
        lat=9.8433,
        lon=76.9763,
        dem_path="data/domain/idukki_small_utm.tif",
        crs="EPSG:32643",
        domain_geojson="data/domain/simulation_domain.geojson",
        domain_bounds_utm=(607585.5, 993037.3, 721814.0, 1108092.4),
        initial_water_level_m=ParameterValue(
            value=732.62, # FRL of Idukki is 2403.5 ft approx 732m
            unit="m",
            provenance=ProvenanceStatus.PUBLISHED,
            reference="KSEB/CWC published FRL"
        ),
        initial_storage_mcm=ParameterValue(
            value=1996.3,
            unit="MCM",
            provenance=ProvenanceStatus.OBSERVED,
            reference="CWC National Register of Large Dams"
        ),
        dam_height_m=ParameterValue(
            value=168.91,
            unit="m",
            provenance=ProvenanceStatus.OBSERVED,
            reference="CWC National Register of Large Dams"
        )
    )
    
    print(f"\nScenario ID: {scenario.scenario_id}")
    print(f"Scenario Name: {scenario.scenario_name}")
    print(f"Type: {scenario.scenario_type}")
    print(f"Peak Discharge (cms): {max([p.discharge_cms for p in scenario.inflow_hydrograph])}")
    
    print("\n--- VALIDATING PROVENANCE AND SCIENTIFIC HONESTY ---")
    for lim in scenario.limitations:
        print(f"LIMITATION: {lim}")
        
    print("\n--- SERIALIZING TO STANDARDIZED JSON INPUT FOR HYDRODYNAMIC MODEL ---")
    # This JSON string is exactly what will be sent to the Delft3D / SPH model adapter in the future.
    json_output = scenario.model_dump_json(indent=2)
    
    import os
    os.makedirs("data/domain", exist_ok=True)
    with open("data/domain/idukki_scenario.json", "w") as f:
        f.write(json_output)
        
    print(f"Saved standardized input to data/domain/idukki_scenario.json")
    print(f"File size: {len(json_output)} bytes")
    
if __name__ == "__main__":
    test_idukki_scenario()
