import os
# --- GIS ENVIRONMENT FIX ---
# PostgreSQL/PostGIS installer globally sets PROJ_LIB which conflicts with Python's rasterio/geopandas.
# We unset it here so that rasterio/pyproj use their bundled PROJ databases.
if "PROJ_LIB" in os.environ:
    del os.environ["PROJ_LIB"]
if "PROJ_DATA" in os.environ:
    del os.environ["PROJ_DATA"]
# ---------------------------

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
def health_check():
    return {"status": "alive"}

@app.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    db_status = "unknown"
    postgis_status = "unknown"
    try:
        result = db.execute(text("SELECT postgis_version();")).scalar()
        db_status = "connected"
        postgis_status = result if result else "not installed"
    except Exception as e:
        logger.error(f"Readiness check DB error: {e}")
        db_status = "failed"
        postgis_status = "unknown"

    return {
        "status": "ready" if db_status == "connected" else "unavailable",
        "database": db_status,
        "postgis_version": postgis_status
    }


from app.hydrodynamics.adapter import ModelRegistry

@app.get('/api/v1/models')
def get_models():
    return ModelRegistry.list_models()


from app.schemas import GlacialLakeResponse

@app.get('/api/v1/lakes', response_model=list[GlacialLakeResponse])
def get_lakes(db: Session = Depends(get_db)):
    try:
        query = db.query(models.GlacialLake, ST_AsGeoJSON(models.GlacialLake.geometry).label("geojson")).all()
        results = []
        for lake, geojson_str in query:
            lake_dict = {
                "id": lake.id, "name": lake.name, "latitude": lake.latitude, "longitude": lake.longitude,
                "elevation_m": lake.elevation_m, "area_sq_m": lake.area_sq_m,
                "estimated_depth_m": lake.estimated_depth_m, "estimated_volume_m3": lake.estimated_volume_m3,
                "downstream_river": lake.downstream_river, "source": lake.source, "source_date": lake.source_date,
                "provenance": lake.provenance, "notes": lake.notes,
                "geojson": json.loads(geojson_str) if geojson_str else None
            }
            results.append(lake_dict)
        return results
    except Exception as e:
        logger.error(f"Database error in get_lakes: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

@app.get('/api/v1/lakes/{lake_id}', response_model=GlacialLakeResponse)
def get_lake(lake_id: str, db: Session = Depends(get_db)):
    try:
        lake, geojson_str = db.query(models.GlacialLake, ST_AsGeoJSON(models.GlacialLake.geometry).label("geojson")).filter(models.GlacialLake.id == lake_id).first()
        if not lake:
            raise HTTPException(status_code=404, detail='Lake not found')
        lake_dict = {
            "id": lake.id, "name": lake.name, "latitude": lake.latitude, "longitude": lake.longitude,
            "elevation_m": lake.elevation_m, "area_sq_m": lake.area_sq_m,
            "estimated_depth_m": lake.estimated_depth_m, "estimated_volume_m3": lake.estimated_volume_m3,
            "downstream_river": lake.downstream_river, "source": lake.source, "source_date": lake.source_date,
            "provenance": lake.provenance, "notes": lake.notes,
            "geojson": json.loads(geojson_str) if geojson_str else None
        }
        return lake_dict
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database error in get_lake: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

@app.get("/api/v1/dams", response_model=list[schemas.DamResponse])
def get_dams(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Fetch all dams with their geometries as GeoJSON"""
    try:
        query = db.query(models.Dam, ST_AsGeoJSON(models.Dam.geometry).label("geojson")).offset(skip).limit(limit).all()
        results = []
        for dam, geojson_str in query:
            dam_dict = {
                "id": dam.id, "name": dam.name, "river": dam.river, "state": dam.state,
                "height_m": dam.height_m, "capacity_mcm": dam.capacity_mcm,
                "latest_storage_mcm": dam.capacity_mcm, "last_updated": dam.created_at,
                "created_at": dam.created_at, "geojson": json.loads(geojson_str) if geojson_str else None
            }
            results.append(dam_dict)
        return results
    except Exception as e:
        logger.error(f"Database error in get_dams: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

@app.get("/api/v1/dams/{dam_id}", response_model=schemas.DamResponse)
def get_dam(dam_id: str, db: Session = Depends(get_db)):
    """Fetch a specific dam by ID"""
    try:
        result = db.query(models.Dam, ST_AsGeoJSON(models.Dam.geometry).label("geojson")).filter(models.Dam.id == dam_id).first()
        if result:
            dam, geojson_str = result
            return {
                "id": dam.id, "name": dam.name, "river": dam.river, "state": dam.state,
                "height_m": dam.height_m, "capacity_mcm": dam.capacity_mcm,
                "latest_storage_mcm": dam.capacity_mcm, "last_updated": dam.created_at,
                "created_at": dam.created_at, "geojson": json.loads(geojson_str) if geojson_str else None
            }
        raise HTTPException(status_code=404, detail="Dam not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database error in get_dam: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

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
        logger.error(f"Database error in create_simulation: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

def _get_simulation_state(sim_id: str):
    try:
        from app.services.simulation_service import SimulationService
        return SimulationService.get_state(sim_id)
    except Exception as e:
        logger.error(f"Database error while fetching simulation state: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

@app.get("/api/v1/simulations/{sim_id}", response_model=schemas.SimulationStatusResponse)
def get_simulation_status(sim_id: str):
    state = _get_simulation_state(sim_id)
    if not state:
        raise HTTPException(status_code=404, detail="Simulation not found")
        
    return {
        "simulation_id": state["simulation_id"],
        "status": state["status"],
        "current_stage": state.get("current_stage"),
        "progress": state.get("progress"),
        "error": state.get("error"),
        "requested_model": state.get("requested_model"),
        "actual_model": state.get("actual_model")
    }

@app.get("/api/v1/simulations/{sim_id}/results", response_model=schemas.SimulationResultsResponse)
def get_simulation_results(sim_id: str):
    state = _get_simulation_state(sim_id)
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
    state = _get_simulation_state(sim_id)
    if not state or state["status"] != "COMPLETED":
        raise HTTPException(status_code=404, detail="Simulation not found or not completed")
    path = state.get("results", {}).get("extent_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="GeoJSON not found")
    return FileResponse(path, media_type="application/geo+json")

@app.get("/api/v1/simulations/{sim_id}/impact")
def get_simulation_impact(sim_id: str):
    state = _get_simulation_state(sim_id)
    if not state or state["status"] != "COMPLETED":
        raise HTTPException(status_code=404, detail="Simulation not found or not completed")
    path = state.get("results", {}).get("impact_summary_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Impact summary not found")
    return FileResponse(path, media_type="application/json")

@app.get("/api/v1/simulations/{sim_id}/satellite")
def get_simulation_satellite(sim_id: str):
    state = _get_simulation_state(sim_id)
    if not state or state["status"] != "COMPLETED":
        raise HTTPException(status_code=404, detail="Simulation not found or not completed")
    path = state.get("results", {}).get("satellite_validation_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Satellite validation not found")
    return FileResponse(path, media_type="application/json")


from app.exports import export_to_shapefile_zip, export_to_kml, export_impact_csv, export_full_package, generate_summary_json

@app.get('/api/v1/simulations/{sim_id}/exports')
def get_exports_metadata(sim_id: str):
    state = _get_simulation_state(sim_id)
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
    state = _get_simulation_state(sim_id)
    if not state or state['status'] != 'COMPLETED': raise HTTPException(status_code=404, detail='Not found')
    path = state.get('results', {}).get('extent_path')
    if not path or not os.path.exists(path): raise HTTPException(status_code=404, detail='Not found')
    return FileResponse(path, media_type='application/geo+json', filename=f'JALDRISHTI_{sim_id}_extent.geojson')

@app.get('/api/v1/simulations/{sim_id}/export/extent/shp')
def export_extent_shp(sim_id: str):
    state = _get_simulation_state(sim_id)
    if not state or state['status'] != 'COMPLETED': raise HTTPException(status_code=404, detail='Not found')
    path = state.get('results', {}).get('extent_path')
    if not path or not os.path.exists(path): raise HTTPException(status_code=404, detail='Not found')
    zip_path = export_to_shapefile_zip(path, sim_id)
    return FileResponse(zip_path, media_type='application/zip', filename=f'JALDRISHTI_{sim_id}_shapefile.zip')

@app.get('/api/v1/simulations/{sim_id}/export/extent/kml')
def export_extent_kml(sim_id: str):
    state = _get_simulation_state(sim_id)
    if not state or state['status'] != 'COMPLETED': raise HTTPException(status_code=404, detail='Not found')
    path = state.get('results', {}).get('extent_path')
    if not path or not os.path.exists(path): raise HTTPException(status_code=404, detail='Not found')
    kml_path = export_to_kml(path, sim_id)
    return FileResponse(kml_path, media_type='application/vnd.google-earth.kml+xml', filename=f'JALDRISHTI_{sim_id}_extent.kml')

@app.get('/api/v1/simulations/{sim_id}/export/depth/geotiff')
def export_depth_geotiff(sim_id: str):
    state = _get_simulation_state(sim_id)
    if not state or state['status'] != 'COMPLETED': raise HTTPException(status_code=404, detail='Not found')
    path = state.get('results', {}).get('depth_path')
    if not path or not os.path.exists(path): raise HTTPException(status_code=404, detail='Not found')
    return FileResponse(path, media_type='image/tiff', filename=f'JALDRISHTI_{sim_id}_depth.tif')

@app.get('/api/v1/simulations/{sim_id}/export/arrival/geotiff')
def export_arrival_geotiff(sim_id: str):
    state = _get_simulation_state(sim_id)
    if not state or state['status'] != 'COMPLETED': raise HTTPException(status_code=404, detail='Not found')
    path = state.get('results', {}).get('arrival_path')
    if not path or not os.path.exists(path): raise HTTPException(status_code=404, detail='Not found')
    return FileResponse(path, media_type='image/tiff', filename=f'JALDRISHTI_{sim_id}_arrival.tif')

@app.get('/api/v1/simulations/{sim_id}/export/impact/csv')
def export_impact_csv_ep(sim_id: str):
    state = _get_simulation_state(sim_id)
    if not state or state['status'] != 'COMPLETED': raise HTTPException(status_code=404, detail='Not found')
    path = state.get('results', {}).get('impact_summary_path')
    if not path or not os.path.exists(path): raise HTTPException(status_code=404, detail='Not found')
    csv_path = export_impact_csv(path, sim_id)
    return FileResponse(csv_path, media_type='text/csv', filename=f'JALDRISHTI_{sim_id}_impact.csv')

@app.get('/api/v1/simulations/{sim_id}/export/impact/json')
def export_impact_json(sim_id: str):
    state = _get_simulation_state(sim_id)
    if not state or state['status'] != 'COMPLETED': raise HTTPException(status_code=404, detail='Not found')
    path = state.get('results', {}).get('impact_summary_path')
    if not path or not os.path.exists(path): raise HTTPException(status_code=404, detail='Not found')
    return FileResponse(path, media_type='application/json', filename=f'JALDRISHTI_{sim_id}_impact.json')

@app.get('/api/v1/simulations/{sim_id}/export/summary/json')
def export_summary_json(sim_id: str):
    state = _get_simulation_state(sim_id)
    if not state or state['status'] != 'COMPLETED': raise HTTPException(status_code=404, detail='Not found')
    impact_path = state.get('results', {}).get('impact_summary_path')
    sat_path = state.get('results', {}).get('satellite_validation_path')
    summary_path = generate_summary_json(state, impact_path, sat_path)
    return FileResponse(summary_path, media_type='application/json', filename=f'JALDRISHTI_{sim_id}_summary.json')

@app.get('/api/v1/simulations/{sim_id}/export/package')
def export_package(sim_id: str):
    state = _get_simulation_state(sim_id)
    if not state or state['status'] != 'COMPLETED': raise HTTPException(status_code=404, detail='Not found')
    pkg_path = export_full_package(state)
    return FileResponse(pkg_path, media_type='application/zip', filename=f'JALDRISHTI_{sim_id}.zip')
