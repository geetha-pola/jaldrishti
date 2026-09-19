import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import engine, Base, SessionLocal
from app.models import Dam, GlacialLake
from geoalchemy2.elements import WKTElement
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migrations():
    logger.info("Running migrations...")
    Base.metadata.create_all(bind=engine)
    logger.info("Tables created.")
    
    db = SessionLocal()
    
    # 1. Seed Dam
    existing_dam = db.query(Dam).filter(Dam.name == "Idukki Dam").first()
    if not existing_dam:
        logger.info("Seeding Idukki Dam (Reference Data)")
        idukki = Dam(
            name="Idukki Dam",
            river="Periyar",
            state="Kerala",
            height_m=168.91,
            capacity_mcm=1996.3,
            latitude=9.843,
            longitude=76.976,
            geometry=WKTElement("POINT(76.976 9.843)", srid=4326),
            source="Seed/Reference Data",
            source_date="2026-09-01"
        )
        db.add(idukki)
    
    # 2. Seed Glacial Lake
    existing_lake = db.query(GlacialLake).filter(GlacialLake.name == "South Lhonak Lake (Sample)").first()
    if not existing_lake:
        logger.info("Seeding South Lhonak Lake (Stress-Test Data)")
        lhonak = GlacialLake(
            name="South Lhonak Lake (Sample)",
            latitude=27.915,
            longitude=88.196,
            elevation_m=5200.0,
            area_sq_m=1.67e6,
            estimated_depth_m=50.0,
            estimated_volume_m3=8.35e7,
            downstream_river="Teesta River",
            geometry=WKTElement("POINT(88.196 27.915)", srid=4326),
            source="Sample Satellite Observation",
            source_date="2026-09-01",
            provenance="ESTIMATED",
            notes="Sample lake representing South Lhonak lake for stress testing."
        )
        db.add(lhonak)
        
    db.commit()
    db.close()
    logger.info("Migration complete.")

if __name__ == "__main__":
    run_migrations()
