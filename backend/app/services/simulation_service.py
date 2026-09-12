import os
import json
import uuid
import logging
from datetime import datetime
from app import schemas
from app.scenarios.models import StandardizedModelInput
from app.hydrodynamics.adapter import ModelRegistry
from app.gis.impact_analysis import ImpactAnalyzer
from app.satellite.validation import SatelliteValidator

# We will use a simple file-based state store for this milestone
STATE_DIR = "data/simulations"
os.makedirs(STATE_DIR, exist_ok=True)

class SimulationService:
    @staticmethod
    def get_state_path(sim_id: str) -> str:
        return os.path.join(STATE_DIR, f"{sim_id}.json")

    @staticmethod
    def _save_state(sim_id: str, state: dict):
        with open(SimulationService.get_state_path(sim_id), 'w') as f:
            json.dump(state, f, indent=4)

    @staticmethod
    def get_state(sim_id: str) -> dict:
        path = SimulationService.get_state_path(sim_id)
        if not os.path.exists(path):
            return None
        with open(path, 'r') as f:
            return json.load(f)

    @staticmethod
    def create_simulation(req: schemas.SimulationRequest) -> str:
        # Validate hazard type
        if req.hazard_type not in ["DAM_BREAK"]:
            raise ValueError(f"Unsupported hazard type: {req.hazard_type}")

        if not req.dam_id or req.dam_id.strip() == "":
            raise ValueError("Invalid dam ID")
            
        model_type = req.model_type or "BASELINE_DIFFUSIVE_WAVE"
        try:
            adapter = ModelRegistry.get_adapter(model_type)
        except ValueError as e:
            raise ValueError(f"Unsupported model type: {model_type}")
            
        if not adapter.is_available:
            raise ValueError(f"Model {model_type} runtime is unavailable in current environment")
            
        sim_id = f"SIM-{uuid.uuid4().hex[:6]}"
        
        state = {
            "simulation_id": sim_id,
            "status": "QUEUED",
            "current_stage": "INITIALIZATION",
            "progress": 0.0,
            "error": None,
            "request": req.dict(),
            "requested_model": model_type,
            "actual_model": model_type,
            "results": {}
        }
        
        SimulationService._save_state(sim_id, state)
        return sim_id

    @staticmethod
    def run_simulation(sim_id: str):
        state = SimulationService.get_state(sim_id)
        if not state:
            return
            
        try:
            state["status"] = "RUNNING"
            state["current_stage"] = "LOADING_SCENARIO"
            state["progress"] = 10.0
            SimulationService._save_state(sim_id, state)
            
            scenario_path = 'data/domain/idukki_scenario.json'
            if not os.path.exists(scenario_path):
                raise FileNotFoundError(f"Scenario file not found: {scenario_path}")
                
            with open(scenario_path, 'r') as f:
                scenario_data = json.load(f)
                
            model_input = StandardizedModelInput(**scenario_data)
            
            state["current_stage"] = "HYDRODYNAMIC_SIMULATION"
            state["progress"] = 30.0
            SimulationService._save_state(sim_id, state)
            
            model_type = state.get("requested_model", "BASELINE_DIFFUSIVE_WAVE")
            adapter = ModelRegistry.get_adapter(model_type)
            if not adapter.is_available:
                raise RuntimeError(f"Runtime for {model_type} is unavailable")
                
            # Allow model adapter to prepare input specific to it (e.g XML for SPH)
            adapter.prepare_input(model_input, output_dir="data/hydro_results")
            
            # Execute Model
            result = adapter.run(model_input, output_dir="data/hydro_results")
            
            # Store paths
            extent_path = result.flood_extent_geojson
            depth_path = result.max_depth_tif
            arrival_path = result.arrival_time_tif
            
            state["results"]["extent_path"] = extent_path
            state["results"]["depth_path"] = depth_path
            state["results"]["arrival_path"] = arrival_path
            state["results"]["max_depth_m"] = result.max_simulated_depth_m
            state["results"]["max_velocity_mps"] = result.max_simulated_velocity_mps
            
            # --- IMPACT ANALYSIS STAGE ---
            state["current_stage"] = "IMPACT_ANALYSIS"
            state["progress"] = 60.0
            SimulationService._save_state(sim_id, state)
            
            # In a real system, we'd pass proper paths
            impact_analyzer = ImpactAnalyzer(
                extent_path=extent_path,
                depth_path=depth_path,
                arrival_path=arrival_path,
                output_dir="data/impact_results"
            )
            
            impact_summary, impact_path = impact_analyzer.run_analysis(
                sim_id=result.simulation_id,
                scenario_id=model_input.scenario_id
            )
            state["results"]["impact_summary_path"] = impact_path
            
            # --- SATELLITE VALIDATION STAGE ---
            state["current_stage"] = "SATELLITE_VALIDATION"
            state["progress"] = 80.0
            SimulationService._save_state(sim_id, state)
            
            event_date = state["request"].get("event_date")
            satellite_validator = SatelliteValidator(output_dir="data/satellite_results")
            
            sat_summary = satellite_validator.validate_simulation(
                sim_id=result.simulation_id,
                modeled_extent_path=extent_path,
                event_date=event_date
            )
            
            # Path to the saved validation summary
            sat_path = os.path.join("data/satellite_results", f"{result.simulation_id}_satellite_validation.json")
            state["results"]["satellite_validation_path"] = sat_path
            
            # --- COMPLETION ---
            state["status"] = "COMPLETED"
            state["current_stage"] = "COMPLETED"
            state["progress"] = 100.0
            SimulationService._save_state(sim_id, state)
            
        except Exception as e:
            logging.error(f"Simulation {sim_id} failed: {str(e)}", exc_info=True)
            state["status"] = "FAILED"
            state["error"] = str(e)
            SimulationService._save_state(sim_id, state)
