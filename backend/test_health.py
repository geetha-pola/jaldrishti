from app.main import health_check, readiness_check, get_dams, get_dam
from fastapi import HTTPException
import json

class DummySession:
    def execute(self, query):
        class Result:
            def scalar(self):
                return "3.3.0"
        return Result()

class DummyDamSession:
    def query(self, *args, **kwargs):
        class QueryChain:
            def offset(self, val): return self
            def limit(self, val): return self
            def filter(self, *args): return self
            def all(self):
                class DummyDam:
                    id = 1
                    name = "Idukki Dam"
                    river = "Periyar"
                    state = "Kerala"
                    height_m = 168.91
                    capacity_mcm = 1996.3
                    latest_storage_mcm = 1500.0
                    last_updated = None
                    created_at = None
                return [(DummyDam(), '{"type": "Point", "coordinates": [76.9763, 9.8433]}')]
                
            def first(self):
                return self.all()[0]
        return QueryChain()

def test_read_health():
    # Test Liveness
    response_alive = health_check()
    assert response_alive["status"] == "alive"

    # Test Readiness DB failure case
    class FailSession:
        def execute(self, query):
            raise Exception("No DB connection")

    response_fail = readiness_check(FailSession())
    assert response_fail["status"] == "unavailable"
    assert response_fail["database"] == "failed"

    # Test Readiness DB success case
    response_success = readiness_check(DummySession())
    assert response_success["status"] == "ready"
    assert response_success["postgis_version"] == "3.3.0"
    print("Health and readiness check tests passed!")

def test_get_dams():
    # Test router logic with mocked DB
    dams = get_dams(skip=0, limit=10, db=DummyDamSession())
    assert len(dams) == 1
    assert dams[0]["name"] == "Idukki Dam"
    assert dams[0]["geojson"]["type"] == "Point"
    print("Get dams logic passed!")

def test_get_dam():
    dam = get_dam(dam_id="DAM-123456", db=DummyDamSession())
    assert dam["name"] == "Idukki Dam"
    assert dam["height_m"] == 168.91
    print("Get dam logic passed!")

if __name__ == "__main__":
    test_read_health()
    test_get_dams()
    test_get_dam()
    print("All mock tests passed successfully!")
