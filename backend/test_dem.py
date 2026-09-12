import os
import sys
import logging
import requests

# Patch requests to disable SSL verify in sandbox
original_request = requests.Session.request
def patched_request(*args, **kwargs):
    kwargs['verify'] = False
    return original_request(*args, **kwargs)
requests.Session.request = patched_request

# Ensure backend directory is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.gis.dem_acquisition import DEMProcessor

logging.basicConfig(level=logging.INFO)

def test_dem_pipeline():
    processor = DEMProcessor(output_dir="data/dem")
    
    # Idukki Dam Coordinates
    lat = 9.8433
    lon = 76.9763
    
    # 1. Test AOI Generation
    bbox = processor.define_aoi(lat, lon, buffer_degrees=0.01) # Use smaller buffer for test speed
    print(f"Generated AOI for Idukki Dam: {bbox}")
    
    # 2. Test Discovery
    assets = processor.discover_dem_data(bbox)
    print(f"Discovered {len(assets)} DEM assets for the AOI.")
    
    if assets:
        print(f"First asset ID: {assets[0]['id']}")
        print(f"First asset URL: {assets[0]['url']}")
        
        # 3. Test Download & Processing
        print("Starting processing pipeline (this may download real DEM data)...")
        result = processor.process_dem(lat, lon, "Idukki_Dam", buffer_degrees=0.01)
        print("\n=== PIPELINE RESULT ===")
        for k, v in result.items():
            print(f"{k}: {v}")
    else:
        print("No assets found. Skipping download test.")

if __name__ == "__main__":
    test_dem_pipeline()
