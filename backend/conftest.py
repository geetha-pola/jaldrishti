import pytest
from sqlalchemy import text
from app.database import engine

@pytest.fixture(scope="function", autouse=True)
def skip_if_db_unavailable(request):
    # Only skip if the test marker is requires_db, or if it's an integration test that touches API
    # Since we don't have a marker, we'll just check if it's in test_api_integration.py or test_glof.py or test_exports.py
    # and if the db is down, skip.
    test_module = request.node.module.__name__
    if test_module in ["test_api_integration", "test_glof", "test_exports"]:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as e:
            pytest.skip(f"PostgreSQL/PostGIS is unavailable: {e}")
