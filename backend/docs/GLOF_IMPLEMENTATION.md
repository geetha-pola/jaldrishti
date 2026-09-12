# GLOF Implementation in JALDRISHTI

This document outlines the implementation of the Glacial Lake Outburst Flood (GLOF) workflow within the JALDRISHTI framework.

## 1. GLOF Workflow
The GLOF workflow is integrated natively alongside the Dam Break workflow using the shared `StandardizedModelInput` and `HydrodynamicModelAdapter` architecture.
1. **Lake Selection**: The user selects a lake from the `/api/v1/lakes` registry.
2. **Lake Characterization**: Physical attributes (area, depth, volume, provenance) are fetched and presented.
3. **Trigger Assessment**: Evidence of triggers (avalanches, extreme rainfall) are reviewed.
4. **Scenario Generation**: The `GLOFScenarioGenerator` calculates the resulting outburst hydrograph.
5. **Hydrodynamic Simulation**: The standard `BASELINE_DIFFUSIVE_WAVE` adapter propagates the breach downstream.
6. **Impact & Validation**: Standard APIs calculate populations affected and perform S1 satellite validation.

## 2. Distinction between GLOF and Dam Break
- **Dam Break** usually relies on engineered dimensions (height, precise spillway geometry, known failure modes). 
- **GLOF** scenarios heavily rely on *estimated* glacial lake volumes and empirical peak discharge envelopes for natural moraine dams, as the bathymetry and dam-structure geometry are rarely explicitly known.

## 3. Data Sources & Provenance
Because glacial lakes are remote, their dimensions are often estimated via satellite imagery (Area) and empirical Area-Volume relationships. 
The system rigorously enforces provenance tracking (`ProvenanceStatus`):
- `OBSERVED`: Direct measurement (e.g., in-situ bathymetry).
- `PUBLISHED`: Values from established literature.
- `ESTIMATED`: Remote-sensing derivations.
- `ENGINEER_DEFINED`: Parameters explicitly provided by the user for stress testing.
- `ASSUMED`: Default physical constants.

Sample dataset provided: **South Lhonak Lake (Sample)**
- Volume: `8.35e7 m³` (`ESTIMATED`)
- Depth: `50.0 m` (`ESTIMATED`)

## 4. Equations and References
**Peak Discharge ($Q_p$) Estimation**:
The peak discharge is an empirical estimate using the relationship established for moraine-dammed lakes:
`Q_p = 0.00013 * (V)^{1.04}`
*(Source: Costa, 1988)*

This equation uses lake/outburst water volume ($V$). It is not a universal physical law, and site-specific GLOF behavior may differ substantially.

**Outburst Hydrograph**:
An idealized triangular hydrograph is generated for scenario simulation, conserving the defined scenario volume:
`T_{base} = \frac{2V}{Q_p}`
The peak is assumed to occur rapidly (e.g., at 20% of $T_{base}$).

Volume conservation here is a mathematical conservation of the defined scenario volume, NOT proof that the hydrograph is physically realistic.

## 5. Model Distinctions
- **BASELINE_DIFFUSIVE_WAVE**: A custom, fast 2D approximation that natively executes in the Python backend. It handles both Dam Break and GLOF scenarios.
- **SPH (Smooth Particle Hydrodynamics)**: A particle-based engine ideal for highly explosive breaches (like catastrophic GLOFs). The integration boundary is built, but the runtime is currently uninstalled.
- **Delft3D**: Flexible mesh 2D/3D SWE solver. The integration boundary is built, but the runtime is currently uninstalled.

## 6. Known Limitations
- The empirical $Q_p$ formula may under-estimate or over-estimate site-specific structural failures.
- The 2D Diffusive Wave baseline caps velocity artificially at 30 m/s for numerical stability in steep mountainous terrain.
- It assumes a 100% volume release for absolute stress testing.

## IMPORTANT SCIENTIFIC RULE
**JALDRISHTI does not predict exactly when a GLOF will occur. It simulates the downstream consequences of a defined or estimated outburst scenario.** All outputs are mathematical scenario estimates.
