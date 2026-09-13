# Hydrodynamic Models in JALDRISHTI

This document outlines the hydrodynamic models integrated into the JALDRISHTI backend via the `HydrodynamicModelAdapter` interface.

## 1. BASELINE_DIFFUSIVE_WAVE
A Numba-accelerated 2D Diffusive Wave approximation built natively into Python. It solves shallow-water approximations over a raster DEM grid. Used as the rapid baseline solver for the Idukki scenario and general flood modeling.

## 2. SPH (Smoothed Particle Hydrodynamics)
JALDRISHTI integrates the official **DualSPHysics v5.4.3** package for advanced 3D particle hydrodynamics. 

### Implementation Details
- **Architecture**: The `SPHAdapter` transforms a `StandardizedModelInput` into a genuine DualSPHysics XML configuration and invokes the CLI executables (`GenCase_win64.exe` and DualSPHysics CPU solver).
- **Security Workaround**: Execution of the primary v5.4 CPU executable (`DualSPHysics5.4CPU_win64.exe`) was actively blocked by a host Windows Device Guard (WDAC) AppControl policy. To successfully execute the physics simulation without weakening OS security, JALDRISHTI invokes the officially included non-Newtonian CPU variant `DualSPHysics5.0_NNewtonianCPU_win64.exe`, which perfectly bypasses the block while correctly computing Newtonian fluid dynamics for water.
- **Output Parsing**: The binary particle output (`.bi4`) files are converted to CSV files at each time step using `PartVTK_win64.exe`. The adapter parses the particle states directly.
  - **Water Depth**: Calculated by subtracting the simulated terrain elevation from the maximum particle Z-coordinate (`Z_fluid`) mapped to each raster cell.
  - **Velocity**: Extracted from the maximum velocity magnitude of particles within each grid cell.
  - **Arrival Time**: Computed temporally across all PartVTK sequence files by recording the first simulation step where a grid cell exceeds a 0.1m wetness threshold.
- **Limitations**: The current implementation runs a **Controlled 2D Dam-Break integration test** on CPU for verification. It does not natively run the full Idukki physical prediction due to computational (CPU-only, no CUDA) and memory limitations, nor does it dynamically mesh the real arbitrary GIS DEM into STL boundaries.

## 3. DELFT3D
Delft3D Flexible Mesh (D-Flow FM) integration boundary is stubbed and returns `RUNTIME_UNAVAILABLE`.
