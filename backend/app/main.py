from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from geoalchemy2.functions import ST_AsGeoJSON
import json

from .database import engine, get_db, Base
from . import models, schemas
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to create all database tables
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully.")
except Exception as e:
    logger.warning(f"Could not connect to the database to create tables: {e}")

app = FastAPI(title="JALDRISHTI API", version="1.0.0")

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    db_status = "unknown"
    postgis_status = "unknown"
    try:
        result = db.execute(text("SELECT postgis_version();")).scalar()
        db_status = "connected"
        postgis_status = result if result else "not installed"
    except Exception as e:
        db_status = f"failed: {str(e)}"
        postgis_status = "unknown"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "postgis_version": postgis_status
    }

@app.get("/api/v1/dams", response_model=list[schemas.DamResponse])
def get_dams(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Fetch all dams with their geometries as GeoJSON"""
    try:
        query = db.query(models.Dam, ST_AsGeoJSON(models.Dam.location).label("geojson")).offset(skip).limit(limit).all()
        results = []
        for dam, geojson_str in query:
            dam_dict = {
                "id": dam.id, "name": dam.name, "river": dam.river, "state": dam.state,
                "height_m": dam.height_m, "capacity_mcm": dam.capacity_mcm,
                "latest_storage_mcm": dam.latest_storage_mcm, "last_updated": dam.last_updated,
                "created_at": dam.created_at, "geojson": json.loads(geojson_str) if geojson_str else None
            }
            results.append(dam_dict)
        return results
    except Exception as e:
        logger.warning(f"Database unavailable for get_dams, returning mock data. Error: {e}")
        return [
            {
                "id": 1, "name": "Idukki Dam", "river": "Periyar", "state": "Kerala",
                "height_m": 168.91, "capacity_mcm": 1996.3, "latest_storage_mcm": 1500.0,
                "last_updated": None, "created_at": "2026-09-01T00:00:00",
                "geojson": {"type": "Point", "coordinates": [76.9763, 9.8433]}
            },
            {
                "id": 2, "name": "Mullaperiyar Dam", "river": "Periyar", "state": "Kerala",
                "height_m": 53.6, "capacity_mcm": 443.23, "latest_storage_mcm": 300.0,
                "last_updated": None, "created_at": "2026-09-01T00:00:00",
                "geojson": {"type": "Point", "coordinates": [77.1472, 9.5286]}
            }
        ]

@app.get("/api/v1/dams/{dam_id}", response_model=schemas.DamResponse)
def get_dam(dam_id: int, db: Session = Depends(get_db)):
    """Fetch a specific dam by ID"""
    try:
        result = db.query(models.Dam, ST_AsGeoJSON(models.Dam.location).label("geojson")).filter(models.Dam.id == dam_id).first()
        if result:
            dam, geojson_str = result
            return {
                "id": dam.id, "name": dam.name, "river": dam.river, "state": dam.state,
                "height_m": dam.height_m, "capacity_mcm": dam.capacity_mcm,
                "latest_storage_mcm": dam.latest_storage_mcm, "last_updated": dam.last_updated,
                "created_at": dam.created_at, "geojson": json.loads(geojson_str) if geojson_str else None
            }
    except Exception as e:
        logger.warning(f"Database unavailable for get_dam, returning mock data. Error: {e}")
        
    # Fallback mock data
    if dam_id == 1:
        return {
            "id": 1, "name": "Idukki Dam", "river": "Periyar", "state": "Kerala",
            "height_m": 168.91, "capacity_mcm": 1996.3, "latest_storage_mcm": 1500.0,
            "last_updated": None, "created_at": "2026-09-01T00:00:00",
            "geojson": {"type": "Point", "coordinates": [76.9763, 9.8433]}
        }
    elif dam_id == 2:
        return {
            "id": 2, "name": "Mullaperiyar Dam", "river": "Periyar", "state": "Kerala",
            "height_m": 53.6, "capacity_mcm": 443.23, "latest_storage_mcm": 300.0,
            "last_updated": None, "created_at": "2026-09-01T00:00:00",
            "geojson": {"type": "Point", "coordinates": [77.1472, 9.5286]}
        }
    raise HTTPException(status_code=404, detail="Dam not found")

from fastapi import BackgroundTasks
from app.services.simulation_service import SimulationService

@app.post("/api/v1/simulations", response_model=schemas.SimulationResponse)
def create_simulation(req: schemas.SimulationRequest, background_tasks: BackgroundTasks):
    try:
        sim_id = SimulationService.create_simulation(req)
        # Dispatch background task
        background_tasks.add_task(SimulationService.run_simulation, sim_id)
        return {"simulation_id": sim_id, "status": "QUEUED"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/simulations/{sim_id}", response_model=schemas.SimulationStatusResponse)
def get_simulation_status(sim_id: str):
    state = SimulationService.get_state(sim_id)
    if not state:
        raise HTTPException(status_code=404, detail="Simulation not found")
        
    return {
        "simulation_id": state["simulation_id"],
        "status": state["status"],
        "current_stage": state.get("current_stage"),
        "progress": state.get("progress"),
        "error": state.get("error")
    }

@app.get("/api/v1/simulations/{sim_id}/results", response_model=schemas.SimulationResultsResponse)
def get_simulation_results(sim_id: str):
    state = SimulationService.get_state(sim_id)
    if not state:
        raise HTTPException(status_code=404, detail="Simulation not found")
        
    if state["status"] != "COMPLETED":
        raise HTTPException(status_code=400, detail="Simulation is not completed")
        
    res = state.get("results", {})
    return {
        "simulation_id": state["simulation_id"],
        "status": state["status"],
        "extent_path": res.get("extent_path"),
        "depth_path": res.get("depth_path"),
        "arrival_path": res.get("arrival_path"),
        "impact_summary_path": res.get("impact_summary_path"),
        "satellite_validation_path": res.get("satellite_validation_path"),
        "max_depth_m": res.get("max_depth_m"),
        "max_velocity_mps": res.get("max_velocity_mps")
    }

import os
from fastapi.responses import FileResponse

@app.get("/api/v1/simulations/{sim_id}/geojson")
def get_simulation_geojson(sim_id: str):
    state = SimulationService.get_state(sim_id)
    if not state or state["status"] != "COMPLETED":
        raise HTTPException(status_code=404, detail="Simulation not found or not completed")
    path = state.get("results", {}).get("extent_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="GeoJSON not found")
    return FileResponse(path, media_type="application/geo+json")

@app.get("/api/v1/simulations/{sim_id}/impact")
def get_simulation_impact(sim_id: str):
    state = SimulationService.get_state(sim_id)
    if not state or state["status"] != "COMPLETED":
        raise HTTPException(status_code=404, detail="Simulation not found or not completed")
    path = state.get("results", {}).get("impact_summary_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Impact summary not found")
    return FileResponse(path, media_type="application/json")

@app.get("/api/v1/simulations/{sim_id}/satellite")
def get_simulation_satellite(sim_id: str):
    state = SimulationService.get_state(sim_id)
    if not state or state["status"] != "COMPLETED":
        raise HTTPException(status_code=404, detail="Simulation not found or not completed")
    path = state.get("results", {}).get("satellite_validation_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Satellite validation not found")
    return FileResponse(path, media_type="application/json")


from app.exports import export_to_shapefile_zip, export_to_kml, export_impact_csv, export_full_package, generate_summary_json

@app.get('/api/v1/simulations/{sim_id}/exports')
def get_exports_metadata(sim_id: str):
    state = SimulationService.get_state(sim_id)
    if not state or state['status'] != 'COMPLETED':
        raise HTTPException(status_code=404, detail='Simulation not found or not completed')
    
    base_url = f'/api/v1/simulations/{sim_id}/export'
    return {
        'simulation_id': sim_id,
        'exports': [
            {'name': 'Flood Extent GeoJSON', 'format': 'geojson', 'url': f'{base_url}/extent/geojson'},
            {'name': 'Flood Extent Shapefile', 'format': 'shp', 'url': f'{base_url}/extent/shp'},
            {'name': 'Flood Extent KML', 'format': 'kml', 'url': f'{base_url}/extent/kml'},
            {'name': 'Flood Depth GeoTIFF', 'format': 'geotiff', 'url': f'{base_url}/depth/geotiff'},
            {'name': 'Arrival Time GeoTIFF', 'format': 'geotiff', 'url': f'{base_url}/arrival/geotiff'},
            {'name': 'Affected Places CSV', 'format': 'csv', 'url': f'{base_url}/impact/csv'},
            {'name': 'Impact Summary JSON', 'format': 'json', 'url': f'{base_url}/impact/json'},
            {'name': 'Simulation Summary JSON', 'format': 'json', 'url': f'{base_url}/summary/json'},
            {'name': 'Complete Result Package', 'format': 'zip', 'url': f'{base_url}/package'}
        ]
    }

@app.get('/api/v1/simulations/{sim_id}/export/extent/geojson')
def export_extent_geojson(sim_id: str):
    state = SimulationService.get_state(sim_id)
    if not state or state['status'] != 'COMPLETED': raise HTTPException(status_code=404, detail='Not found')
    path = state.get('results', {}).get('extent_path')
    if not path or not os.path.exists(path): raise HTTPException(status_code=404, detail='Not found')
    return FileResponse(path, media_type='application/geo+json', filename=f'JALDRISHTI_{sim_id}_extent.geojson')

@app.get('/api/v1/simulations/{sim_id}/export/extent/shp')
def export_extent_shp(sim_id: str):
    state = SimulationService.get_state(sim_id)
    if not state or state['status'] != 'COMPLETED': raise HTTPException(status_code=404, detail='Not found')
    path = state.get('results', {}).get('extent_path')
    if not path or not os.path.exists(path): raise HTTPException(status_code=404, detail='Not found')
    zip_path = export_to_shapefile_zip(path, sim_id)
    return FileResponse(zip_path, media_type='application/zip', filename=f'JALDRISHTI_{sim_id}_shapefile.zip')

@app.get('/api/v1/simulations/{sim_id}/export/extent/kml')
def export_extent_kml(sim_id: str):
    state = SimulationService.get_state(sim_id)
    if not state or state['status'] != 'COMPLETED': raise HTTPException(status_code=404, detail='Not found')
    path = state.get('results', {}).get('extent_path')
    if not path or not os.path.exists(path): raise HTTPException(status_code=404, detail='Not found')
    kml_path = export_to_kml(path, sim_id)
    return FileResponse(kml_path, media_type='application/vnd.google-earth.kml+xml', filename=f'JALDRISHTI_{sim_id}_extent.kml')

@app.get('/api/v1/simulations/{sim_id}/export/depth/geotiff')
def export_depth_geotiff(sim_id: str):
    state = SimulationService.get_state(sim_id)
    if not state or state['status'] != 'COMPLETED': raise HTTPException(status_code=404, detail='Not found')
    path = state.get('results', {}).get('depth_path')
    if not path or not os.path.exists(path): raise HTTPException(status_code=404, detail='Not found')
    return FileResponse(path, media_type='image/tiff', filename=f'JALDRISHTI_{sim_id}_depth.tif')

@app.get('/api/v1/simulations/{sim_id}/export/arrival/geotiff')
def export_arrival_geotiff(sim_id: str):
    state = SimulationService.get_state(sim_id)
    if not state or state['status'] != 'COMPLETED': raise HTTPException(status_code=404, detail='Not found')
    path = state.get('results', {}).get('arrival_path')
    if not path or not os.path.exists(path): raise HTTPException(status_code=404, detail='Not found')
    return FileResponse(path, media_type='image/tiff', filename=f'JALDRISHTI_{sim_id}_arrival.tif')

@app.get('/api/v1/simulations/{sim_id}/export/impact/csv')
def export_impact_csv_ep(sim_id: str):
    state = SimulationService.get_state(sim_id)
    if not state or state['status'] != 'COMPLETED': raise HTTPException(status_code=404, detail='Not found')
    path = state.get('results', {}).get('impact_summary_path')
    if not path or not os.path.exists(path): raise HTTPException(status_code=404, detail='Not found')
    csv_path = export_impact_csv(path, sim_id)
    return FileResponse(csv_path, media_type='text/csv', filename=f'JALDRISHTI_{sim_id}_impact.csv')

@app.get('/api/v1/simulations/{sim_id}/export/impact/json')
def export_impact_json(sim_id: str):
    state = SimulationService.get_state(sim_id)
    if not state or state['status'] != 'COMPLETED': raise HTTPException(status_code=404, detail='Not found')
    path = state.get('results', {}).get('impact_summary_path')
    if not path or not os.path.exists(path): raise HTTPException(status_code=404, detail='Not found')
    return FileResponse(path, media_type='application/json', filename=f'JALDRISHTI_{sim_id}_impact.json')

@app.get('/api/v1/simulations/{sim_id}/export/summary/json')
def export_summary_json(sim_id: str):
    state = SimulationService.get_state(sim_id)
    if not state or state['status'] != 'COMPLETED': raise HTTPException(status_code=404, detail='Not found')
    impact_path = state.get('results', {}).get('impact_summary_path')
    sat_path = state.get('results', {}).get('satellite_validation_path')
    summary_path = generate_summary_json(state, impact_path, sat_path)
    return FileResponse(summary_path, media_type='application/json', filename=f'JALDRISHTI_{sim_id}_summary.json')

@app.get('/api/v1/simulations/{sim_id}/export/package')
def export_package(sim_id: str):
    state = SimulationService.get_state(sim_id)
    if not state or state['status'] != 'COMPLETED': raise HTTPException(status_code=404, detail='Not found')
    pkg_path = export_full_package(state)
    return FileResponse(pkg_path, media_type='application/zip', filename=f'JALDRISHTI_{sim_id}.zip')
