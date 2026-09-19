# JALDRISHTI Deployment & Reproducibility Guide

This document outlines how to set up JALDRISHTI on a clean machine for development or production use.

## Prerequisites
- Python 3.10+
- PostgreSQL 13+
- PostGIS 3+
- Git

*(Note: Docker is not strictly required. The application can run natively on Windows/Linux environments).*

## 1. Installation

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/geetha-pola/jaldrishti.git
   cd jaldrishti/backend
   ```

2. **Create and Activate a Virtual Environment:**
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On Linux/Mac:
   source venv/bin/activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## 2. Environment Configuration

1. Copy the example configuration:
   ```bash
   cp .env.example .env
   ```
2. Edit `.env` to match your local database credentials:
   ```env
   DATABASE_URL=postgresql://<user>:<password>@localhost:5432/jaldrishti
   HOST=0.0.0.0
   PORT=8000
   ```
   *Security Note: NEVER commit `.env` to the repository. It is excluded in `.gitignore`.*

## 3. Database Setup

1. **Create the Database & Enable PostGIS (psql):**
   ```sql
   CREATE DATABASE jaldrishti;
   \c jaldrishti;
   CREATE EXTENSION postgis;
   ```

2. **Provision the Schema and Seed Data:**
   Run the initialization script from the `backend` directory. This uses SQLAlchemy `create_all()` to provision tables and inserts the required baseline records (e.g., Idukki Dam, South Lhonak Lake).
   ```bash
   python scripts/migrate.py
   ```
   *(Note: For future schema evolution, an Alembic migration system can be introduced alongside this).*

## 4. Backend Startup

1. Run the FastAPI application using Uvicorn:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
2. The API will be available at `http://localhost:8000/api/v1`.
3. Verify Health/Readiness:
   - `GET /health` : Returns liveness (process alive).
   - `GET /ready` : Returns backend readiness, indicating PostgreSQL reachability.

## 5. Frontend Startup

The frontend is a vanilla static web application (HTML/CSS/JS) using Leaflet. No complex bundlers (like React/Vite) are required.

1. **Configure API Endpoint:**
   By default, `frontend/config.js` points to `http://localhost:8000/api/v1`. Update this if your backend is deployed remotely.

2. **Serve the Static Files:**
   Serve the `frontend/` directory using any static web server. E.g.:
   ```bash
   cd ../frontend
   python -m http.server 8080
   ```
3. Access the dashboard at `http://localhost:8080`.

## 6. External Services & Failures

JALDRISHTI interacts with external mapping and satellite services.
- **Google Earth Engine (GEE):** Used by `SatelliteValidator`. It is *optional*. If credentials are not present or an observation is unavailable, the system safely reports `NO SUITABLE SATELLITE OBSERVATION AVAILABLE` rather than crashing.
- **Copernicus DEM:** Used for domain generation. 
- **OpenStreetMap:** Used for impact infrastructure.

The simulation pipeline continues gracefully if satellite imagery is unavailable. If the database goes offline during operations, endpoints return explicit `503 Service Unavailable`.

## 7. Data Directories

At runtime, JALDRISHTI creates directories to store intermediate outputs. These are ignored by Git.
- `backend/data/domain/`
- `backend/data/hydro_results/`
- `backend/data/impact_results/`
- `backend/data/satellite_results/`

*(Important: Large GeoTIFF outputs are not stored in PostgreSQL. The DB retains explicit file references only).*

## 8. Security & Production Considerations
- **CORS:** Ensure `app/main.py` CORS settings are restricted to your frontend domain in production.
- **Scoped Artifacts:** Exports and JSON artifacts are securely scoped by `simulation_id` UUIDs. Path traversal is prevented.
- **No Mock Data:** The system will refuse to start correctly if the database is unprovisioned, preventing accidental fake data presentation.
