import json
import glob
from app.gis.impact_analysis import ImpactAnalyzer

def run():
    print("--- INITIATING IMPACT ANALYSIS MILESTONE ---")
    
    # Get the latest simulation extent
    extent_files = glob.glob("data/hydro_results/*_extent.geojson")
    if not extent_files:
        print("No hydrodynamic results found!")
        return
        
    import os
    latest_extent = max(extent_files, key=os.path.getctime)
    prefix = latest_extent.replace("_extent.geojson", "")
    sim_id = os.path.basename(prefix)
    
    depth_path = f"{prefix}_max_depth.tif"
    arrival_path = f"{prefix}_arrival.tif"
    
    print(f"Using simulation results for: {sim_id}")
    print(f"Extent: {latest_extent}")
    print(f"Depth Raster: {depth_path}")
    print(f"Arrival Raster: {arrival_path}")
    
    analyzer = ImpactAnalyzer(
        extent_path=latest_extent,
        depth_path=depth_path,
        arrival_path=arrival_path
    )
    
    print("\n--- PERFORMING SPATIAL INTERSECTION WITH OSM ---")
    summary, summary_path = analyzer.run_analysis(sim_id=sim_id, scenario_id="SCEN-IDU-c2c7e4")
    
    print("\n--- FLOOD IMPACT ANALYSIS ---")
    
    print("\nNearest affected places\n")
    print(f"{'Place':<20} {'Type':<12} {'Distance':<12} {'Arrival':<10}")
    print("-" * 55)
    
    places = summary.get('places', [])
    for p in places[:10]:  # Show top 10
        dist = f"{p['distance_from_source_km']:.1f} km"
        arr = f"{int(p['flood_arrival_minutes'])} min"
        print(f"{p['name'][:19]:<20} {p['type'].capitalize()[:11]:<12} {dist:<12} {arr:<10}")
        
    print("\nFLOOD ARRIVAL TIMELINE\n")
    print("Dam")
    for p in places[:5]:  # Timeline for top 5
        arr = f"{int(p['flood_arrival_minutes'])} min"
        print(" |")
        print(" V")
        print(f"{arr} -> {p['name']}")
        
    print(f"\nSaved impact summary to: {summary_path}")
    
    print("\n--- SCIENTIFIC HONESTY / LIMITATIONS ---")
    for lim in summary['limitations']:
        print(f"LIMITATION: {lim}")
        
if __name__ == "__main__":
    run()
