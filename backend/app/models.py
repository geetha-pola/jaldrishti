from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, JSON
from geoalchemy2 import Geometry
from .database import Base
from sqlalchemy.sql import func
import uuid

class Dam(Base):
    __tablename__ = "dams"

    id = Column(String, primary_key=True, default=lambda: f"DAM-{uuid.uuid4().hex[:6]}", index=True)
    name = Column(String, index=True)
    river = Column(String, index=True)
    state = Column(String, index=True)
    height_m = Column(Float)
    capacity_mcm = Column(Float)
    latitude = Column(Float)
    longitude = Column(Float)
    geometry = Column(Geometry('POINT', srid=4326))
    source = Column(String)
    source_date = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class GlacialLake(Base):
    __tablename__ = "glacial_lakes"

    id = Column(String, primary_key=True, default=lambda: f"LAKE-{uuid.uuid4().hex[:6]}", index=True)
    name = Column(String, index=True)
    latitude = Column(Float)
    longitude = Column(Float)
    elevation_m = Column(Float)
    area_sq_m = Column(Float)
    estimated_depth_m = Column(Float)
    estimated_volume_m3 = Column(Float)
    downstream_river = Column(String)
    geometry = Column(Geometry('POINT', srid=4326))
    source = Column(String)
    source_date = Column(String)
    provenance = Column(String)
    notes = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Scenario(Base):
    __tablename__ = "scenarios"

    scenario_id = Column(String, primary_key=True, default=lambda: f"SCENARIO-{uuid.uuid4().hex[:6]}", index=True)
    scenario_type = Column(String)
    parameter_metadata = Column(JSON)
    provenance = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Simulation(Base):
    __tablename__ = "simulations"

    simulation_id = Column(String, primary_key=True, default=lambda: f"SIM-{uuid.uuid4().hex[:6]}", index=True)
    hazard_type = Column(String)
    dam_id = Column(String, ForeignKey("dams.id"), nullable=True)
    lake_id = Column(String, ForeignKey("glacial_lakes.id"), nullable=True)
    scenario_id = Column(String, ForeignKey("scenarios.scenario_id"), nullable=True)
    
    requested_model = Column(String)
    actual_model = Column(String)
    status = Column(String, default="QUEUED")
    progress = Column(Float, default=0.0)
    current_stage = Column(String)
    
    # Result references
    extent_path = Column(String, nullable=True)
    depth_path = Column(String, nullable=True)
    velocity_path = Column(String, nullable=True)
    arrival_path = Column(String, nullable=True)
    impact_summary_path = Column(String, nullable=True)
    satellite_validation_path = Column(String, nullable=True)
    export_package_path = Column(String, nullable=True)
    
    error_information = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
