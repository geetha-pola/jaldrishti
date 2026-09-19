import os
import json
import csv
import tempfile

def export_impact_csv(impact_json_path: str, sim_id: str) -> str:
    if not os.path.exists(impact_json_path):
        raise FileNotFoundError("Impact JSON file not found.")

    with open(impact_json_path, 'r') as f:
        data = json.load(f)
        
    csv_path = os.path.join(tempfile.gettempdir(), f"{sim_id}_affected_places.csv")
    
    places = data.get("places", [])
    
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["place_name", "place_type", "distance_km", "model_estimated_arrival_time_min", "severity", "max_depth_m"])
        
        for p in places:
            writer.writerow([
                p.get("name", "Unknown"),
                p.get("type", "Unknown"),
                round(p.get("distance_from_source_km", 0), 2),
                round(p.get("flood_arrival_minutes", 0), 2),
                p.get("impact_level", "UNKNOWN"),
                round(p.get("max_depth_m", 0), 2)
            ])
            
    return csv_path
