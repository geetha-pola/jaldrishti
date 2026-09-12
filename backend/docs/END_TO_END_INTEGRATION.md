# JALDRISHTI End-to-End Integration (M15)

## 1. Architecture & Canonical Pipeline

JALDRISHTI acts as an on-demand inundation simulation framework. The canonical pipeline implemented in M15 connects existing modules strictly through the database, without bypassing any logic.

The canonical flow is:
USER → FRONTEND → FASTAPI → POSTGRESQL / POSTGIS → DAM / LAKE SELECTION → SCENARIO → DATA ACQUISITION → DEM / TERRAIN PROCESSING → HYDRODYNAMIC MODEL → FLOOD EXTENT / DEPTH / ARRIVAL → IMPACT ANALYSIS → SATELLITE VALIDATION → RESULT PERSISTENCE → FRONTEND RESULTS → EXPORTS

### Known Limitations
**The currently executable hydrodynamic path is the 2D Diffusive Wave Baseline Solver. SPH and Delft3D remain separate integration boundaries when their runtimes are unavailable.**

**Simulation results for the current Idukki scenario are hypothetical stress-test outputs and are not validated operational predictions.**

## 2. Request Flow & Database Interaction

1. **Selection**: The user selects a dam/lake on the Frontend Map. The Frontend fetches this list via `GET /api/v1/dams` or `GET /api/v1/lakes`, strictly reading from PostGIS geometries (`EPSG:4326`).
2. **Execution Request**: The Frontend requests a simulation via `POST /api/v1/simulations`.
3. **Database Insertion**: The API creates a new `Simulation` row in PostgreSQL with `status="QUEUED"`. 
4. **Background Task**: The `SimulationService.run_simulation` grabs the `Simulation` row from the database and begins processing, locking states and updating `progress`.

## 3. Model Selection
The `ModelRegistry` resolves the requested model string (e.g., `BASELINE_DIFFUSIVE_WAVE`). If the user specifies `SPH` or `Delft3D` and the local environment lacks their external executables, the adapter accurately throws a runtime-unavailable error. The system **does not** silently fall back to the baseline solver.

## 4. Result Persistence
- **State Tracking**: `SimulationService` commits the `current_stage` and `progress` fields to PostgreSQL during processing (e.g. `LOADING_SCENARIO`, `HYDRODYNAMIC_SIMULATION`, `IMPACT_ANALYSIS`).
- **Heavy Artifacts**: GeoJSON extents, GeoTIFF depth/arrival rasters, and zipped Shapefiles are saved to the filesystem (`data/hydro_results/`, `data/impact_results/`). The PostgreSQL database strictly stores explicit object/file path references to prevent table bloat.

## 5. Impact Analysis
Impact Analysis ingests the exact baseline solver output. Using OpenStreetMap integration, it calculates the **Model-Estimated Flood Arrival** for downstream infrastructure. The language used specifically highlights that these are *model estimates*, not predictive certainties. 

## 6. Satellite Validation
Satellite validation automatically runs. For the hypothetical extreme scenario, there may be no matching real-world Sentinel-1 event date. The validation gracefully reports `NO SUITABLE SATELLITE OBSERVATION AVAILABLE FOR THIS SCENARIO` instead of inventing data.

## 7. Error Handling
- **Database Unavailable**: Emits `HTTP 503 Service Unavailable`.
- **Invalid ID**: `404` or `400`.
- **Simulation Failure**: The simulation transitions to `FAILED` in the database, with `error_information` captured.

## 8. Frontend Flow
The Frontend dynamically polls `GET /api/v1/simulations/{id}/status`. Upon `COMPLETED`, it renders the final impact layers, GeoJSON extent, arrival times, and generates a unified zip export.
