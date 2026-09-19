import json
import rasterio
import numpy as np
import geopandas as gpd

class ComparisonService:
    @staticmethod
    def compare(result_sph, result_d3d):
        try:
            # 1. Compare Extents (IoU)
            iou = 0.0
            sph_area = result_sph.flooded_area_sq_meters
            d3d_area = result_d3d.flooded_area_sq_meters
            
            try:
                sph_gdf = gpd.read_file(result_sph.flood_extent_geojson)
                d3d_gdf = gpd.read_file(result_d3d.flood_extent_geojson)
                
                if not sph_gdf.empty and not d3d_gdf.empty:
                    # Union all geometries
                    sph_geom = sph_gdf.geometry.unary_union
                    d3d_geom = d3d_gdf.geometry.unary_union
                    
                    intersection = sph_geom.intersection(d3d_geom).area
                    union = sph_geom.union(d3d_geom).area
                    if union > 0:
                        iou = intersection / union
            except Exception as e:
                pass
                
            return {
                "sph": {
                    "max_depth_m": result_sph.max_simulated_depth_m,
                    "max_velocity_mps": result_sph.max_simulated_velocity_mps,
                    "flooded_area_sq_meters": sph_area
                },
                "delft3d": {
                    "max_depth_m": result_d3d.max_simulated_depth_m,
                    "max_velocity_mps": result_d3d.max_simulated_velocity_mps,
                    "flooded_area_sq_meters": d3d_area
                },
                "iou": iou * 100.0,
                "note": "Impact analysis based on Delft3D result."
            }
        except Exception as e:
            return {"error": str(e)}
