import os
import json
import uuid
import logging
from datetime import datetime
from app import schemas
from app.scenarios.models import StandardizedModelInput
from app.scenarios.glof_generator import GLOFScenarioGenerator
from app.hydrodynamics.adapter import ModelRegistry
from app.gis.impact_analysis import ImpactAnalyzer
from app.satellite.validation import SatelliteValidator

from app.database import SessionLocal
from app.models import Simulation

class SimulationService:
    @staticmethod
    def _get_state_dict(sim: Simulation) -> dict:
        if not sim:
            return None
        return {
            "simulation_id": sim.simulation_id,
            "status": sim.status,
            "current_stage": sim.current_stage,
            "progress": sim.progress,
            "error": sim.error_information,
            "request": {
                "hazard_type": sim.hazard_type,
                "dam_id": sim.dam_id,
                "lake_id": sim.lake_id,
                "scenario_id": sim.scenario_id,
                "model_type": sim.requested_model
            },
            "requested_model": sim.requested_model,
            "actual_model": sim.actual_model,
            "results": {
                "extent_path": sim.extent_path,
                "depth_path": sim.depth_path,
                "arrival_path": sim.arrival_path,
                "impact_summary_path": sim.impact_summary_path,
                "satellite_validation_path": sim.satellite_validation_path,
                "export_package_path": sim.export_package_path,
                "max_depth_m": None, # Kept for API compatibility
                "max_velocity_mps": None # Kept for API compatibility
            }
        }

    @staticmethod
    def get_state(sim_id: str) -> dict:
        db = SessionLocal()
        try:
            sim = db.query(Simulation).filter(Simulation.simulation_id == sim_id).first()
            return SimulationService._get_state_dict(sim)
        except Exception as e:
            logger.error(f"Failed to get simulation state: {e}")
            raise e
        finally:
            db.close()

    @staticmethod
    def create_simulation(req: schemas.SimulationRequest) -> str:
        if req.hazard_type not in ["DAM_BREAK", "GLOF"]:
            raise ValueError(f"Unsupported hazard type: {req.hazard_type}")

        if req.hazard_type == "DAM_BREAK" and (not req.dam_id or req.dam_id.strip() == ""):
            raise ValueError("Invalid dam ID")
            
        if req.hazard_type == "GLOF" and (not req.lake_id or req.lake_id.strip() == ""):
            raise ValueError("Invalid lake ID")
            
        model_type = req.model_type or "BASELINE_DIFFUSIVE_WAVE"
        try:
            adapter = ModelRegistry.get_adapter(model_type)
        except ValueError as e:
            raise ValueError(f"Unsupported model type: {model_type}")
            
        db = SessionLocal()
        try:
            if not adapter.is_available:
                sim = Simulation(
                    hazard_type=req.hazard_type,
                    dam_id=req.dam_id if req.hazard_type == "DAM_BREAK" else None,
                    lake_id=req.lake_id if req.hazard_type == "GLOF" else None,
                    requested_model=model_type,
                    actual_model=None,
                    status="RUNTIME_UNAVAILABLE",
                    current_stage="FAILED",
                    progress=0.0,
                    error_information=f"Runtime for {model_type} is unavailable in the current environment."
                )
                db.add(sim)
                db.commit()
                return sim.simulation_id
                
            sim = Simulation(
                hazard_type=req.hazard_type,
                dam_id=req.dam_id if req.hazard_type == "DAM_BREAK" else None,
                lake_id=req.lake_id if req.hazard_type == "GLOF" else None,
                requested_model=model_type,
                actual_model=model_type,
                status="QUEUED",
                current_stage="INITIALIZATION",
                progress=0.0
            )
            db.add(sim)
            db.commit()
            sim_id = sim.simulation_id
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
        
        return sim_id

    @staticmethod
    def run_simulation(sim_id: str):
        db = SessionLocal()
        try:
            sim = db.query(Simulation).filter(Simulation.simulation_id == sim_id).first()
            if not sim:
                return
                
            sim.status = "RUNNING"
            sim.current_stage = "LOADING_SCENARIO"
            sim.progress = 10.0
            db.commit()
            
            if sim.hazard_type == "GLOF":
                from app.models import GlacialLake
                lake_db = db.query(GlacialLake).filter(GlacialLake.id == sim.lake_id).first()
                if not lake_db:
                    raise ValueError(f"Lake {sim.lake_id} not found in DB")
                lake = {
                    "id": lake_db.id,
                    "latitude": lake_db.latitude,
                    "longitude": lake_db.longitude,
                    "estimated_volume_m3": lake_db.estimated_volume_m3,
                    "estimated_depth_m": lake_db.estimated_depth_m
                }
                
                dem_path = 'data/domain/projected_dem.tif'
                import rasterio
                with rasterio.open(dem_path) as src:
                    b = src.bounds
                    bounds_utm = (b.left, b.bottom, b.right, b.top)
                    crs = src.crs.to_string()
                    
                model_input = GLOFScenarioGenerator.generate_scenario(lake, dem_path, bounds_utm, crs)
            else:
                scenario_path = 'data/domain/idukki_scenario.json'
                if not os.path.exists(scenario_path):
                    raise FileNotFoundError(f"Scenario file not found: {scenario_path}")
                    
                with open(scenario_path, 'r') as f:
                    scenario_data = json.load(f)
                    
                model_input = StandardizedModelInput(**scenario_data)
            
            sim.current_stage = "HYDRODYNAMIC_SIMULATION"
            sim.progress = 30.0
            db.commit()
            
            model_type = sim.requested_model or "BASELINE_DIFFUSIVE_WAVE"
            adapter = ModelRegistry.get_adapter(model_type)
            if not adapter.is_available:
                raise RuntimeError(f"Runtime for {model_type} is unavailable")
                
            adapter.prepare_input(model_input, output_dir="data/hydro_results")
            result = adapter.run(model_input, output_dir="data/hydro_results")
            
            sim.extent_path = result.flood_extent_geojson
            sim.depth_path = result.max_depth_tif
            sim.arrival_path = result.arrival_time_tif
            db.commit()
            
            # --- IMPACT ANALYSIS STAGE ---
            sim.current_stage = "IMPACT_ANALYSIS"
            sim.progress = 60.0
            db.commit()
            
            impact_analyzer = ImpactAnalyzer(
                extent_path=result.flood_extent_geojson,
                depth_path=result.max_depth_tif,
                arrival_path=result.arrival_time_tif,
                output_dir="data/impact_results"
            )
            
            impact_summary, impact_path = impact_analyzer.run_analysis(
                sim_id=result.simulation_id,
                scenario_id=model_input.scenario_id
            )
            sim.impact_summary_path = impact_path
            db.commit()
            
            # --- SATELLITE VALIDATION STAGE ---
            sim.current_stage = "SATELLITE_VALIDATION"
            sim.progress = 80.0
            db.commit()
            
            satellite_validator = SatelliteValidator(output_dir="data/satellite_results")
            sat_summary = satellite_validator.validate_simulation(
                sim_id=result.simulation_id,
                modeled_extent_path=result.flood_extent_geojson,
                event_date=None
            )
            
            sat_path = os.path.join("data/satellite_results", f"{result.simulation_id}_satellite_validation.json")
            sim.satellite_validation_path = sat_path
            
            # --- COMPLETION ---
            sim.status = "COMPLETED"
            sim.current_stage = "COMPLETED"
            sim.progress = 100.0
            sim.completed_at = datetime.utcnow()
            db.commit()
            
        except Exception as e:
            logging.error(f"Simulation {sim_id} failed: {str(e)}", exc_info=True)
            db.rollback()
            sim = db.query(Simulation).filter(Simulation.simulation_id == sim_id).first()
            if sim:
                sim.status = "FAILED"
                sim.error_information = str(e)
                sim.completed_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()
