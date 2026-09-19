import os
import sys
import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.gis.terrain_analysis import TerrainAnalyzer
from app.gis.dem_acquisition import DEMProcessor, DEMConfig

@pytest.fixture
def analyzer():
    return TerrainAnalyzer(output_dir="data/test_domain")

def test_utm_epsg(analyzer):
    # Idukki Dam coordinates (9.8433, 76.9763) -> UTM Zone 43N -> EPSG:32643
    epsg = analyzer._get_utm_epsg(9.8433, 76.9763)
    assert epsg == "EPSG:32643"
    
    # Negative lat (southern hemisphere) -> 32700 + zone
    epsg_south = analyzer._get_utm_epsg(-9.0, 76.9763)
    assert epsg_south == "EPSG:32743"

def test_terrain_analysis_missing_pysheds():
    import app.gis.terrain_analysis as ta
    original_pysheds = ta.PYSHEDS_AVAILABLE
    try:
        ta.PYSHEDS_AVAILABLE = False
        analyzer = ta.TerrainAnalyzer(output_dir="data/test_domain")
        with pytest.raises(Exception, match="pysheds is required"):
            analyzer.analyze_terrain("dummy.tif", 9.8, 76.9)
    finally:
        ta.PYSHEDS_AVAILABLE = original_pysheds
