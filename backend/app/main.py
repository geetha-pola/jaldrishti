from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from .database import engine, get_db, Base
from . import models
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to create all database tables (For production, consider using Alembic for migrations)
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully.")
except Exception as e:
    logger.warning(f"Could not connect to the database to create tables: {e}")

app = FastAPI(title="JALDRISHTI API", version="1.0.0")

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    # Verify DB connectivity
    db_status = "unknown"
    postgis_status = "unknown"
    try:
        # Check PostGIS extension
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
