import math
from typing import List
from .models import HydrographPoint, ParameterValue, ProvenanceStatus

class BreachHydrographGenerator:
    """
    Generates an outflow hydrograph from dam breach parameters.
    """
    
    @staticmethod
    def calculate_froehlich_1995(volume_m3: float, head_m: float) -> tuple[float, float]:
        """
        Froehlich (1995) empirical equations for earthen dam breaches.
        
        Equation (Peak Discharge): Qp = 0.607 * (Vw^0.295) * (hw^1.24)
        Equation (Time of Failure): tf = 0.00254 * (Vw^0.53) * (hw^-0.9)
        
        Args:
            volume_m3: Volume of water above breach invert (m^3)
            head_m: Depth of water above breach invert (m)
            
        Returns:
            Tuple of (peak_discharge_cms, breach_time_hours)
            
        Limitations:
            - Developed from regression analysis of 63 earthen dam failures.
            - NOT physically applicable to concrete arch dams (like Idukki), gravity dams, or RCC dams.
            - Overestimates failure times for instantaneous structural collapses.
        """
        peak_discharge_cms = 0.607 * (volume_m3 ** 0.295) * (head_m ** 1.24)
        breach_time_hours = 0.00254 * (volume_m3 ** 0.53) * (head_m ** -0.90)
        return peak_discharge_cms, breach_time_hours
        
    @staticmethod
    def generate_triangular_hydrograph(
        volume_m3: float, 
        peak_discharge_cms: float, 
        time_to_peak_hours: float
    ) -> List[HydrographPoint]:
        """
        Creates a simplified triangular hydrograph conserving the total volume.
        
        Area of triangle = 0.5 * base * height
        volume = 0.5 * total_duration_seconds * peak_discharge
        total_duration_seconds = (2 * volume) / peak_discharge
        
        Assumptions:
        - Discharge rises linearly from 0 to Qp over time_to_peak.
        - Discharge falls linearly from Qp to 0 over the remaining duration.
        """
        total_duration_sec = (2.0 * volume_m3) / peak_discharge_cms
        time_to_peak_sec = time_to_peak_hours * 3600.0
        
        if time_to_peak_sec >= total_duration_sec:
            # Prevent impossible geometry: if failure time is extremely slow compared to volume,
            # adjust time to peak to be 1/3 of total duration (typical generic assumption).
            time_to_peak_sec = total_duration_sec / 3.0
            
        points = [
            HydrographPoint(time_seconds=0.0, discharge_cms=0.0),
            HydrographPoint(time_seconds=time_to_peak_sec, discharge_cms=peak_discharge_cms),
            HydrographPoint(time_seconds=total_duration_sec, discharge_cms=0.0)
        ]
        return points
