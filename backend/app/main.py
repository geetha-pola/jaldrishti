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

@app.get("/dams", response_model=list[schemas.DamResponse])
def get_dams(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Fetch all dams with their geometries as GeoJSON"""
    try:
        # We query the Dam model and also extract the location as GeoJSON
        query = db.query(models.Dam, ST_AsGeoJSON(models.Dam.location).label("geojson")).offset(skip).limit(limit).all()
        
        results = []
        for dam, geojson_str in query:
            # We convert the ORM object to a dict, then construct the response
            dam_dict = {
                "id": dam.id,
                "name": dam.name,
                "river": dam.river,
                "state": dam.state,
                "height_m": dam.height_m,
                "capacity_mcm": dam.capacity_mcm,
                "latest_storage_mcm": dam.latest_storage_mcm,
                "last_updated": dam.last_updated,
                "created_at": dam.created_at,
                "geojson": json.loads(geojson_str) if geojson_str else None
            }
            results.append(dam_dict)
            
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/dams/{dam_id}", response_model=schemas.DamResponse)
def get_dam(dam_id: int, db: Session = Depends(get_db)):
    """Fetch a specific dam by ID"""
    try:
        result = db.query(models.Dam, ST_AsGeoJSON(models.Dam.location).label("geojson")).filter(models.Dam.id == dam_id).first()
        if not result:
            raise HTTPException(status_code=404, detail="Dam not found")
            
        dam, geojson_str = result
        return {
            "id": dam.id,
            "name": dam.name,
            "river": dam.river,
            "state": dam.state,
            "height_m": dam.height_m,
            "capacity_mcm": dam.capacity_mcm,
            "latest_storage_mcm": dam.latest_storage_mcm,
            "last_updated": dam.last_updated,
            "created_at": dam.created_at,
            "geojson": json.loads(geojson_str) if geojson_str else None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
