# JALDRISHTI 

**One Platform. Two Hazards. One Common Flood Modelling Workflow.**

JALDRISHTI is an on-demand flood inundation modelling and disaster-management decision-support platform for GLOF and Dam Break scenarios.

## Overview
- **Unified Workflow:** Handles both Glacial Lake Outburst Floods (GLOF) and Dam Break scenarios.
- **Hydrodynamic Simulation:** Integrates with a 2D Diffusive Wave baseline solver.
- **GIS Integration:** Processes Copernicus DEM data and exports standard formats (GeoJSON, KML, GeoTIFF, SHP).
- **Impact Analysis:** Automatically identifies downstream infrastructure and estimates flood arrival times.
- **Satellite Validation:** Validates model extents against Sentinel-1 observations (where available).

## Documentation
- [Deployment & Reproducibility Guide](backend/docs/DEPLOYMENT.md) - Instructions for setting up the backend, database, and frontend.
- [Database Architecture](backend/docs/DATABASE_ARCHITECTURE.md) - Details on PostgreSQL/PostGIS integration.
- [End-to-End Integration](backend/docs/END_TO_END_INTEGRATION.md) - Pipeline architecture and data flow.
- [GLOF Implementation](backend/docs/GLOF_IMPLEMENTATION.md) - Scientific context for the GLOF scenario generator.

## Setup
Please see `backend/docs/DEPLOYMENT.md` for full instructions to deploy the system locally.
