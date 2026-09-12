import os
import glob
from app.satellite.validation import SatelliteValidator

def run():
    print("--- INITIATING SATELLITE VALIDATION MILESTONE ---")
    
    # 1. Find latest flood extent
    geojsons = glob.glob('data/hydro_results/*_extent.geojson')
    if not geojsons:
        print("No flood extent found.")
        return
        
    latest_extent = max(geojsons, key=os.path.getctime)
    sim_id = os.path.basename(latest_extent).replace('_extent.geojson', '')
    
    print(f"Using simulation results for: {sim_id}")
    print(f"Extent: {latest_extent}")
    
    # 2. Run validation (passing None for event_date since it's a hypothetical scenario)
    validator = SatelliteValidator()
    summary = validator.validate_simulation(sim_id, latest_extent, event_date=None)
    
    # 3. Print output format
    print("\n--- SATELLITE VALIDATION ---")
    print(f"\nSatellite:\n{summary['satellite_source']}")
    print(f"\nObserved flood:\n{summary['observed_area_km2']:.2f} km2")
    print(f"\nModelled flood:\n{summary['modeled_area_km2']:.2f} km2")
    print(f"\nSpatial overlap:\n{summary['intersection_area_km2']:.2f} km2")
    print(f"\nAgreement (IoU):\n{summary['iou']:.2f}%")
    print(f"\nValidation status:\n{summary['validation_status']}")
    
    print("\n--- SCIENTIFIC HONESTY / LIMITATIONS ---")
    for limitation in summary.get("limitations", []):
        print(f"LIMITATION: {limitation}")
        
    print(f"\nSaved validation summary to: data/satellite_results/{sim_id}_satellite_validation.json")

if __name__ == "__main__":
    run()
