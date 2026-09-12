# Hydrodynamic Models in JALDRISHTI

This document records the exact state, capability, and execution evidence for the hydrodynamic solvers supported in JALDRISHTI.

## 1. Baseline Diffusive Wave
- **Status**: IMPLEMENTED & EXECUTED
- **Type**: 2D Diffusive Wave Approximation
- **Governing Equations**: Simplified 2D shallow water equations omitting inertial terms. Uses Manning's equation for friction.
- **Runtime**: Native Python with `numba` JIT compilation.
- **Execution Evidence**: Fully executed in all M12-M17 test cases, generating actual output GeoTIFFs (max depth, arrival time) and GeoJSON flood extents from the synthetic Idukki scenario.
- **Input Generation**: Standard raster DEM + Inflow timeseries (m3/s) -> 2D numpy arrays.
- **Output Parsing**: Numpy arrays -> Rasterio GeoTIFF -> Shapely polygons.

## 2. SPH (Smooth Particle Hydrodynamics)
- **Status**: INTEGRATION-READY, RUNTIME-UNAVAILABLE
- **Selected Implementation**: DualSPHysics (v5.2)
- **Rationale**: DualSPHysics is the most defensible open-source SPH engine for free-surface flows (Dam Break/GLOF), natively supporting GPU acceleration and complex 3D boundary interaction, which is critical for realistic catastrophic outburst flows.
- **Governing Equations**: Navier-Stokes equations discretized using weakly compressible SPH (WCSPH).
- **Runtime Requirements**: Requires pre-compiled C++/CUDA binaries (`DualSPHysics5.2`) which are not present in the current containerized environment.
- **Execution Evidence**: NOT EXECUTED.
- **Input Generation**: The `SPHAdapter` generates the necessary GenCase XML file (`sph_case.xml`) translating the duration, gravity, and bounds into DualSPHysics structure.
- **Output Parsing**: If executed, output would require post-processing `PartFluid` VTK/CSV point-cloud files into 2D raster grids by rasterizing particle Z-coordinates (water surface elevation minus terrain elevation).

## 3. Delft3D
- **Status**: INTEGRATION-READY, RUNTIME-UNAVAILABLE
- **Selected Implementation**: Delft3D Flexible Mesh (D-Flow FM)
- **Rationale**: D-Flow FM is the state-of-the-art hydrodynamic engine for flood propagation over complex terrain. It handles 2D shallow-water equations on unstructured grids, making it vastly superior to legacy structured-grid Delft3D-FLOW for dam-break inundation.
- **Governing Equations**: 2D Shallow Water Equations (SWE) on unstructured grids.
- **Runtime Requirements**: Requires the `dflowfm` executable and Deltares runtime libraries, which are not present.
- **Execution Evidence**: NOT EXECUTED.
- **Input Generation**: The `Delft3DAdapter` generates the necessary MDU (Master Definition Unit) and BC (Boundary Condition) files.
- **Output Parsing**: If executed, NetCDF output map files would be parsed via `xarray` to extract maximum water depth and arrival time across the mesh.

## Model Comparison
JALDRISHTI provides a unified comparison endpoint (`/api/v1/simulations/compare`). However, since only the Baseline Diffusive Wave solver is currently executable in this environment, true physical comparison (e.g., IoU, max depth variance) cannot be calculated. The framework correctly returns `RUNTIME_UNAVAILABLE` for the missing engines.

## Known Limitations
The Baseline Diffusive Wave solver is a numerical approximation suitable for early estimation. It lacks momentum conservation (critical for the immediate outburst phase of a Dam Break). It is provided strictly as a placeholder executable pipeline until real SPH/Delft3D runtimes are deployed to the host machine.
