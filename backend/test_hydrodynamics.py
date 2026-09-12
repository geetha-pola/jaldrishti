import json
import logging
from app.hydrodynamics import BaselineHydrodynamicAdapter

logging.basicConfig(level=logging.INFO)

def run():
    print("--- INITIATING HYDRODYNAMIC SIMULATION MILESTONE ---")
    scenario_path = "data/domain/idukki_scenario.json"
    
    print(f"Reading standardized model input from: {scenario_path}")
    adapter = BaselineHydrodynamicAdapter(output_dir="data/hydro_results")
    
    print("\n--- EXECUTING BASELINE SOLVER (BEHIND MODEL ADAPTER) ---")
    result = adapter.execute_simulation(scenario_path)
    
    print("\n--- SIMULATION COMPLETED ---")
    print(f"Simulation ID: {result.simulation_id}")
    print(f"Scenario ID: {result.scenario_id}")
    print(f"Solver Name: {result.solver_name}")
    print(f"Computational Time: {result.computational_time_seconds:.2f} seconds")
    print(f"Timesteps Executed: {result.total_timesteps_executed}")
    print(f"Max Simulated Depth (m): {result.max_simulated_depth_m:.2f}")
    print(f"Max Simulated Velocity (m/s): {result.max_simulated_velocity_mps:.2f}")
    print(f"Flooded Area (sq meters): {result.flooded_area_sq_meters:,.2f}")
    
    print("\n--- RASTER AND VECTOR OUTPUTS ---")
    print(f"Max Depth GeoTIFF: {result.max_depth_tif}")
    print(f"Max Velocity GeoTIFF: {result.max_velocity_tif}")
    print(f"Arrival Time GeoTIFF: {result.arrival_time_tif}")
    print(f"Flood Extent GeoJSON: {result.flood_extent_geojson}")
    
    print("\n--- SCIENTIFIC HONESTY / LIMITATIONS ---")
    for lim in result.limitations:
        print(f"LIMITATION: {lim}")

if __name__ == "__main__":
    run()
