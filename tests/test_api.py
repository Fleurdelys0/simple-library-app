import os
import importlib
import pytest
from fastapi.testclient import TestClient
from config import settings


@pytest.fixture
def client(tmp_path, request):
    # Create a unique per-test DB and ensure api picks it up at import time
    db_file = str(tmp_path / f"api_test_{request.node.name}.db")
    os.environ["LIBRARY_DB_FILE"] = db_file

    import api as api_module
    # Reload api so its global Library() instance uses the test-specific DB
    importlib.reload(api_module)

    test_client = TestClient(api_module.app)
    try:
        yield test_client
    finally:
        # Cleanup DB file and env var after test
        os.environ.pop("LIBRARY_DB_FILE", None)
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except Exception:
                pass


def test_get_books(client):
    response = client.get("/books")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_add_book_with_valid_api_key(client):
    headers = {"X-API-Key": settings.api_key}
    payload = {"isbn": "9780321765723"}
    response = client.post("/books", headers=headers, json=payload)
    assert response.status_code == 200
    assert response.json()["isbn"] == "9780321765723"


def test_add_book_with_invalid_api_key(client):
    headers = {"X-API-Key": "invalid-key"}
    payload = {"isbn": "9780321765723"}
    response = client.post("/books", headers=headers, json=payload)
    assert response.status_code == 403
