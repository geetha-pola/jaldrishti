from app.main import health_check

class DummySession:
    def execute(self, query):
        class Result:
            def scalar(self):
                return "3.3.0"
        return Result()

def test_read_health():
    # Test DB failure case
    class FailSession:
        def execute(self, query):
            raise Exception("No DB connection")

    response_fail = health_check(FailSession())
    assert response_fail["status"] == "degraded"
    assert "failed" in response_fail["database"]

    # Test DB success case
    response_success = health_check(DummySession())
    assert response_success["status"] == "healthy"
    assert response_success["postgis_version"] == "3.3.0"

    print("Health check tests passed successfully (ignoring TestClient httpx issue)!")

if __name__ == "__main__":
    test_read_health()
