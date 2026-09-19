import os
import sys
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.gis.terrain_analysis import TerrainAnalyzer

logging.basicConfig(level=logging.INFO)

def run():
    analyzer = TerrainAnalyzer(output_dir="data/domain")
    
    # Idukki Dam coordinates
    lat = 9.8433
    lon = 76.9763
    
    # Use the 1x1 degree raw Copernicus tile that is already downloaded
    raw_dem_path = "data/dem/Copernicus_DSM_COG_10_N09_00_E076_00_DEM.tif"
    
    print(f"Starting terrain analysis on {raw_dem_path}")
    result = analyzer.analyze_terrain(raw_dem_path, lat, lon, corridor_width_m=2000.0)
    
    print("\n=== TERRAIN ANALYSIS RESULTS ===")
    print(f"Status: {result['status']}")
    print(f"Projected CRS: {result['crs']}")
    print("Statistics:")
    for k, v in result['stats'].items():
        print(f"  {k}: {v}")
    print(f"Simulation Domain saved to: {result['domain_geojson']}")
    print(f"Flow Direction TIF saved to: {result['fdir_tif']}")
    print(f"Flow Accumulation TIF saved to: {result['acc_tif']}")
    print(f"Domain Bounds (UTM): {result['domain_bounds_utm']}")

if __name__ == "__main__":
    run()
