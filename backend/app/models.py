from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from geoalchemy2 import Geometry
from .database import Base
from sqlalchemy.sql import func

class Dam(Base):
    __tablename__ = "dams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    location = Geometry('POINT', srid=4326) # Real coordinates
    height = Column(Float)
    capacity = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class GlacialLake(Base):
    __tablename__ = "glacial_lakes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    location = Geometry('POINT', srid=4326)
    estimated_volume = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class SimulationDomain(Base):
    __tablename__ = "simulation_domains"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    boundary = Geometry('POLYGON', srid=4326) # The downstream corridor
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class FloodResult(Base):
    __tablename__ = "flood_results"

    id = Column(Integer, primary_key=True, index=True)
    simulation_id = Column(String, index=True) # E.g., SIM-025
    hazard_type = Column(String) # GLOF or DAM_BREAK
    flood_extent = Geometry('MULTIPOLYGON', srid=4326) # The max flooded area
    max_depth_raster_path = Column(String) # Reference to GeoTIFF file
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ImpactData(Base):
    __tablename__ = "impact_data"

    id = Column(Integer, primary_key=True, index=True)
    flood_result_id = Column(Integer, ForeignKey("flood_results.id"))
    infrastructure_type = Column(String) # e.g. "road", "building"
    impact_geometry = Geometry('GEOMETRY', srid=4326) # The specific affected infrastructure
    created_at = Column(DateTime(timezone=True), server_default=func.now())
