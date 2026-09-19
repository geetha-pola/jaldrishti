import os
# --- GIS ENVIRONMENT FIX ---
if "PROJ_LIB" in os.environ:
    del os.environ["PROJ_LIB"]
if "PROJ_DATA" in os.environ:
    del os.environ["PROJ_DATA"]
import pyproj
# Explicitly set PROJ_DATA to the pyproj bundled directory so rasterio and gdal pick it up
os.environ["PROJ_DATA"] = pyproj.datadir.get_data_dir()
os.environ["PROJ_LIB"] = pyproj.datadir.get_data_dir()
# ---------------------------

