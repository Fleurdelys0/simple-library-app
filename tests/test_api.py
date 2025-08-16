import pytest
import os
from fastapi.testclient import TestClient

# Set a test-specific environment variable for the database file
# This must be done BEFORE importing the app
os.environ["LIBRARY_DB_FILE"] = "test_api_library.db"

from api import app, settings, library
from database import DATABASE_FILE, initialize_database

# Fixture to ensure a clean database and a fresh in-memory library for each test
@pytest.fixture(autouse=True)
def clean_db_for_api_tests():
    # 1. Clear the database file
    if os.path.exists(DATABASE_FILE):
        os.remove(DATABASE_FILE)
    initialize_database()

    # 2. Clear the in-memory list of the global 'library' instance from api.py
    library.books.clear()

    yield

    # Teardown
    if os.path.exists(DATABASE_FILE):
        os.remove(DATABASE_FILE)


client = TestClient(app)

# --- Test Data ---
VALID_API_KEY = {"X-API-Key": settings.api_key}
INVALID_API_KEY = {"X-API-Key": "invalid-key"}
TEST_ISBN = "9780321765723" # Effective C++
TEST_ISBN_2 = "9780201633610" # Design Patterns

# --- Mocks ---
class MockOpenLibraryResponse:
    def __init__(self, isbn, title, author):
        self.isbn = isbn
        self.title = title
        self.author = author
        self.status_code = 200

    def json(self):
        return {
            f"ISBN:{self.isbn}": {
                "title": self.title,
                "authors": [{"name": self.author}]
            }
        }

def mock_add_book(monkeypatch, isbn, title="Test Title", author="Test Author"):
    """Mocks the httpx.get call to simulate adding a book via Open Library."""
    mock_response = MockOpenLibraryResponse(isbn, title, author)
    monkeypatch.setattr("library.httpx.get", lambda *args, **kwargs: mock_response)

# --- Refactored Tests ---

def test_get_books_empty():
    response = client.get("/books")
    assert response.status_code == 200
    assert response.json() == []

def test_add_and_get_books(monkeypatch):
    # Add two books via the API
    mock_add_book(monkeypatch, TEST_ISBN, "Effective C++", "Scott Meyers")
    client.post("/books", headers=VALID_API_KEY, json={"isbn": TEST_ISBN})

    mock_add_book(monkeypatch, TEST_ISBN_2, "Design Patterns", "Erich Gamma")
    client.post("/books", headers=VALID_API_KEY, json={"isbn": TEST_ISBN_2})

    # Get the list of books
    response = client.get("/books")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["isbn"] == TEST_ISBN
    assert data[1]["isbn"] == TEST_ISBN_2

def test_add_book_security():
    response = client.post("/books", json={"isbn": TEST_ISBN})
    assert response.status_code == 403 # Missing API Key
    response = client.post("/books", headers=INVALID_API_KEY, json={"isbn": TEST_ISBN})
    assert response.status_code == 403 # Invalid API Key

def test_add_book_success(monkeypatch):
    mock_add_book(monkeypatch, TEST_ISBN, "Effective C++", "Scott Meyers")

    response = client.post("/books", headers=VALID_API_KEY, json={"isbn": TEST_ISBN})
    assert response.status_code == 200
    data = response.json()
    assert data["isbn"] == TEST_ISBN
    assert data["title"] == "Effective C++"
    assert data["author"] == "Scott Meyers"

def test_add_duplicate_book(monkeypatch):
    # Add the book once
    mock_add_book(monkeypatch, TEST_ISBN, "Effective C++", "Scott Meyers")
    client.post("/books", headers=VALID_API_KEY, json={"isbn": TEST_ISBN})

    # Try to add it again
    response = client.post("/books", headers=VALID_API_KEY, json={"isbn": TEST_ISBN})
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]

def test_delete_book(monkeypatch):
    # Add a book to be deleted
    mock_add_book(monkeypatch, TEST_ISBN_2, "To Be Deleted", "Author")
    client.post("/books", headers=VALID_API_KEY, json={"isbn": TEST_ISBN_2})

    # Delete it
    response = client.delete(f"/books/{TEST_ISBN_2}", headers=VALID_API_KEY)
    assert response.status_code == 200
    assert response.json() == {"message": "Book removed."}

    # Verify it's gone
    get_response = client.get(f"/books/{TEST_ISBN_2}")
    assert get_response.status_code == 404

def test_delete_book_not_found():
    response = client.delete("/books/nonexistent_isbn", headers=VALID_API_KEY)
    assert response.status_code == 404

def test_update_book(monkeypatch):
    # Add a book to be updated
    mock_add_book(monkeypatch, TEST_ISBN, "Old Title", "Old Author")
    client.post("/books", headers=VALID_API_KEY, json={"isbn": TEST_ISBN})

    # Update it
    update_payload = {"title": "New Title", "author": "New Author"}
    response = client.put(f"/books/{TEST_ISBN}", headers=VALID_API_KEY, json=update_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "New Title"
    assert data["author"] == "New Author"

def test_update_book_not_found():
    update_payload = {"title": "New Title"}
    response = client.put("/books/nonexistent_isbn", headers=VALID_API_KEY, json=update_payload)
    assert response.status_code == 404

def test_update_book_bad_payload(monkeypatch):
    # Add a book
    mock_add_book(monkeypatch, TEST_ISBN, "A Book", "An Author")
    client.post("/books", headers=VALID_API_KEY, json={"isbn": TEST_ISBN})

    # Send empty payload to update
    response = client.put(f"/books/{TEST_ISBN}", headers=VALID_API_KEY, json={})
    assert response.status_code == 400
    assert "Provide title and/or author" in response.json()["detail"]

def test_get_single_book(monkeypatch):
    mock_add_book(monkeypatch, TEST_ISBN, "Effective C++", "Scott Meyers")
    client.post("/books", headers=VALID_API_KEY, json={"isbn": TEST_ISBN})

    response = client.get(f"/books/{TEST_ISBN}")
    assert response.status_code == 200
    data = response.json()
    assert data["isbn"] == TEST_ISBN
    assert data["title"] == "Effective C++"

def test_get_single_book_not_found():
    response = client.get("/books/nonexistent_isbn")
    assert response.status_code == 404

def test_get_stats(monkeypatch):
    mock_add_book(monkeypatch, TEST_ISBN, "Title 1", "Author A")
    client.post("/books", headers=VALID_API_KEY, json={"isbn": TEST_ISBN})
    mock_add_book(monkeypatch, TEST_ISBN_2, "Title 2", "Author B")
    client.post("/books", headers=VALID_API_KEY, json={"isbn": TEST_ISBN_2})

    response = client.get("/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_books"] == 2
    assert data["unique_authors"] == 2

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_export_json(monkeypatch):
    mock_add_book(monkeypatch, TEST_ISBN, "Title 1", "Author A")
    client.post("/books", headers=VALID_API_KEY, json={"isbn": TEST_ISBN})

    response = client.get("/export/json")
    assert response.status_code == 200
    assert "attachment; filename=" in response.headers["content-disposition"]
    data = response.json()
    assert len(data) == 1
    assert data[0]["isbn"] == TEST_ISBN

def test_export_csv(monkeypatch):
    mock_add_book(monkeypatch, TEST_ISBN, "Title 1", "Author A")
    client.post("/books", headers=VALID_API_KEY, json={"isbn": TEST_ISBN})

    response = client.get("/export/csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"] # Use 'in' for broader match
    assert "attachment; filename=" in response.headers["content-disposition"]
    content = response.text
    assert "isbn,title,author" in content
    assert TEST_ISBN in content
