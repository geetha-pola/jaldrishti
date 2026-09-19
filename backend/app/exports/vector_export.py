import os
import zipfile
import tempfile
import geopandas as gpd

def export_to_shapefile_zip(geojson_path: str, sim_id: str) -> str:
    """Converts a GeoJSON to a zipped Shapefile containing all required components."""
    if not os.path.exists(geojson_path):
        raise FileNotFoundError("GeoJSON file not found.")

    gdf = gpd.read_file(geojson_path, engine="pyogrio")
    
    # Create a temporary directory to save the shapefile components
    tmp_dir = tempfile.mkdtemp(prefix=f"shp_{sim_id}_")
    shp_base = os.path.join(tmp_dir, f"{sim_id}_extent.shp")
    
    # Export to Shapefile
    gdf.to_file(shp_base, engine="pyogrio")
    
    # Zip the components
    zip_path = os.path.join(tempfile.gettempdir(), f"{sim_id}_shapefile.zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for ext in ['.shp', '.shx', '.dbf', '.prj']:
            file_path = os.path.join(tmp_dir, f"{sim_id}_extent{ext}")
            if os.path.exists(file_path):
                zipf.write(file_path, arcname=f"{sim_id}_extent{ext}")
                
    return zip_path

def export_to_kml(geojson_path: str, sim_id: str) -> str:
    """Converts a GeoJSON to KML format."""
    if not os.path.exists(geojson_path):
        raise FileNotFoundError("GeoJSON file not found.")

    gdf = gpd.read_file(geojson_path, engine="pyogrio")
    
    # Ensure geographic CRS for KML (Google Earth default is EPSG:4326)
    if gdf.crs and gdf.crs.to_string() != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")
        
    kml_path = os.path.join(tempfile.gettempdir(), f"{sim_id}_extent.kml")
    gdf.to_file(kml_path, driver="KML", engine="pyogrio")
    
    return kml_path
