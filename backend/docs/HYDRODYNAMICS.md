# JALDRISHTI Hydrodynamic Modelling Framework

This document outlines the hydrodynamic modelling architecture integrated into JALDRISHTI to address SIH PS26161 ("Inundation Modelling Using Hydrodynamic Modelling of any River").

## 1. Baseline Diffusive Wave Solver
**Status**: IMPLEMENTED & EXECUTABLE
**Why it exists**: Full Navier-Stokes, SWE, or SPH solvers are computationally intensive and require heavy external binaries (like DualSPHysics or Delft3D). The baseline 2D Diffusive Wave solver was custom-built using Python+Numba to provide a scientifically defensible, fast, lightweight approximation that executes natively within the FastAPI backend environment without external dependencies.
**Methodology / Governing Equations**:
It approximates the 2D Shallow Water Equations by dropping inertial terms, relying on the Diffusive Wave approximation:
`∂h/∂t + ∂(uh)/∂x + ∂(vh)/∂y = 0`
Where velocity is calculated using Manning's equation based on the local water surface gradient:
`V = (1/n) * R^(2/3) * S^(1/2)`
**Input Requirements**: StandardizedModelInput (GeoJSON bounds, Hydrograph arrays, Manning's N).
**Resolution**: ~300m (Copernicus DEM resampled natively for rapid execution).
**Boundary Conditions**: Closed boundaries at the grid edge; inflow boundary assigned dynamically at the dam breach pixel.
**Output Format**: GeoTIFFs (Max Depth, Velocity, Arrival Time) and GeoJSON flood extent.
**Numerical Assumptions**: The velocity is artificially capped at 30 m/s to maintain numerical stability in steep topography (this is NOT a physical limit).
**Known Limitations**: Cannot model highly dynamic wavefronts, hydraulic jumps, or super-critical momentum transfers accurately.

## 2. SPH (Smooth Particle Hydrodynamics)
**Status**: INTEGRATION-READY (RUNTIME-UNAVAILABLE)
**What it is**: A mesh-free Lagrangian method where fluid is represented by discrete particles carrying mass and momentum. Ideal for highly non-linear, splash-heavy dam-break wavefronts.
**Implementation Status**: The adapter (`SPHAdapter`) successfully generates the required `GenCase XML` boundary logic (terrain, gravity, particle spacing). However, the actual DualSPHysics/PySPH C++/CUDA binary is not installed in this environment.
**Governing Equations**: Weakly Compressible Navier-Stokes equations (WCSPH).
**License**: DualSPHysics is open-source (LGPL).

## 3. Delft3D (Flexible Mesh)
**Status**: INTEGRATION-READY (RUNTIME-UNAVAILABLE)
**What it is**: An industry-standard open-source 2D/3D hydrodynamic suite by Deltares. It solves the full Shallow Water Equations using a flexible, unstructured grid.
**Implementation Status**: The adapter (`Delft3DAdapter`) successfully translates the `StandardizedModelInput` into Delft3D Master Definition (`.mdu`) and boundary (`.bc`) configurations. The `dflowfm` executable is required to compute the result but is absent in the host OS.
**Methodology**: Finite-volume solution of the SWE.
**License**: Open-source (GPL).

## Summary
| Model | Status | Actual Execution Evidence |
|---|---|---|
| BASELINE_DIFFUSIVE_WAVE | Executable | `max_depth_m` and `max_velocity_mps` successfully generated |
| SPH | Runtime Unavailable | XML GenCase generated; subprocess skipped |
| DELFT3D | Runtime Unavailable | MDU & BC files generated; subprocess skipped |

*Scientific Disclaimer: The current Idukki Dam scenario represents an "Extreme Hypothetical Stress-Test Scenario". Satellite validation proves mathematical spatial overlap but does NOT prove physical exactness of the baseline diffusive wave numerical approximation.*
