from fastapi.testclient import TestClient
from api import app, settings

client = TestClient(app)


def test_get_books():
    response = client.get("/books")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_add_book_with_valid_api_key():
    headers = {"X-API-Key": settings.api_key}
    payload = {"isbn": "9780321765723"}
    response = client.post("/books", headers=headers, json=payload)
    assert response.status_code == 200
    assert response.json()["isbn"] == "9780321765723"


def test_add_book_with_invalid_api_key():
    headers = {"X-API-Key": "invalid-key"}
    payload = {"isbn": "9780321765723"}
    response = client.post("/books", headers=headers, json=payload)
    assert response.status_code == 403
