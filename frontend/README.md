# JALDRISHTI Complete Frontend Prototype

A complete visual frontend flow for the SIH JALDRISHTI concept.

Tech used in this prototype:
- HTML
- CSS
- JavaScript
- Leaflet
- OpenStreetMap tiles

Included:
Login/dashboard concept, GLOF workflow, Dam Break workflow, data acquisition, preprocessing, simulation domain, scenario generator, model adapter, simulation progress, flood results, propagation timeline, scenario comparison, impact analysis, satellite validation, exports, history, architecture, technology stack and about.

IMPORTANT:
All numerical values are DEMO/PLACEHOLDER values. They are not real model outputs.
The UI is ready to connect to FastAPI, CWC/NWDP, Copernicus DEM/STAC, GEE/Sentinel, SPH/Delft3D and PostgreSQL/PostGIS.


### Offline map note
This version includes an offline SVG map fallback so the map panels remain visible even when the laptop cannot load external Leaflet/OpenStreetMap resources. The map is a UI/demo visualization, not a real GIS result. Real DEM, satellite, and hydrodynamic outputs should replace it when the backend is connected.


### Timeline demo
The Flood Propagation Timeline now responds to the time slider. Increasing time enlarges the demo flood footprint and updates the displayed time/label. This remains a UI demonstration until connected to real hydrodynamic time-step outputs.
