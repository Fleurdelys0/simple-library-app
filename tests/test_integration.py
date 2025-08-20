import pytest
import tempfile
import os
from fastapi.testclient import TestClient

from api import app
from library import Library
from validators import ISBNValidator, TextValidator
import database

# Mark this module as integration to skip by default
pytestmark = pytest.mark.integration

@pytest.fixture
def test_client():
    """Create a test client with a clean database."""
    # Use a temporary database for testing
    test_db = tempfile.mktemp(suffix='.db')
    database.DATABASE_FILE = test_db
    database.initialize_database()
    
    client = TestClient(app)
    yield client
    
    # Cleanup
    if os.path.exists(test_db):
        os.remove(test_db)

def test_full_book_lifecycle(test_client):
    """Test complete book lifecycle: create, read, update, delete."""
    # Create a book
    create_data = {"isbn": "9780134686097"}
    headers = {"X-API-Key": "super-secret-key"}
    
    response = test_client.post("/books", json=create_data, headers=headers)
    assert response.status_code == 200
    book_data = response.json()
    assert book_data["isbn"] == "9780134686097"
    
    # Read the book
    response = test_client.get(f"/books/{book_data['isbn']}")
    assert response.status_code == 200
    retrieved_book = response.json()
    assert retrieved_book["isbn"] == book_data["isbn"]
    
    # Update the book
    update_data = {"title": "Updated Title", "author": "Updated Author"}
    response = test_client.put(f"/books/{book_data['isbn']}", json=update_data, headers=headers)
    assert response.status_code == 200
    updated_book = response.json()
    assert updated_book["title"] == "Updated Title"
    assert updated_book["author"] == "Updated Author"
    
    # Delete the book
    response = test_client.delete(f"/books/{book_data['isbn']}", headers=headers)
    assert response.status_code == 200
    
    # Verify deletion
    response = test_client.get(f"/books/{book_data['isbn']}")
    assert response.status_code == 404

def test_search_functionality(test_client):
    """Test search functionality with multiple books."""
    headers = {"X-API-Key": "super-secret-key"}
    
    # Add multiple books
    books = [
        {"isbn": "9780134686097", "title": "Test Book 1", "author": "Author One"},
        {"isbn": "9780134686098", "title": "Another Book", "author": "Author Two"},
        {"isbn": "9780134686099", "title": "Test Book 3", "author": "Author One"}
    ]
    
    for book in books:
        response = test_client.post("/books", json=book, headers=headers)
        assert response.status_code == 200
    
    # Search by title
    response = test_client.get("/books?q=Test")
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 2  # Should find 2 books with "Test" in title
    
    # Search by author
    response = test_client.get("/books?q=Author One")
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 2  # Should find 2 books by "Author One"

def test_pagination(test_client):
    """Test pagination functionality."""
    headers = {"X-API-Key": "super-secret-key"}
    
    # Add multiple books
    for i in range(25):
        book_data = {
            "isbn": f"978013468609{i:02d}",
            "title": f"Book {i}",
            "author": f"Author {i}"
        }
        response = test_client.post("/books", json=book_data, headers=headers)
        assert response.status_code == 200
    
    # Test paginated response
    response = test_client.get("/books/paginated?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert data["total"] == 25
    assert data["total_pages"] == 3
    assert len(data["items"]) == 10

def test_export_functionality(test_client):
    """Test data export functionality."""
    headers = {"X-API-Key": "super-secret-key"}
    
    # Add a few books
    books = [
        {"isbn": "9780134686097", "title": "Book 1", "author": "Author 1"},
        {"isbn": "9780134686098", "title": "Book 2", "author": "Author 2"}
    ]
    
    for book in books:
        response = test_client.post("/books", json=book, headers=headers)
        assert response.status_code == 200
    
    # Test JSON export
    response = test_client.get("/export/json")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["title"] == "Book 1"
    
    # Test CSV export
    response = test_client.get("/export/csv")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    csv_content = response.text
    assert "isbn,title,author" in csv_content
    assert "Book 1" in csv_content

def test_isbn_validation():
    """Test ISBN validation functionality."""
    # Valid ISBN-10
    assert ISBNValidator.is_valid_isbn("0134686047")
    assert ISBNValidator.is_valid_isbn("013468604X")
    
    # Valid ISBN-13
    assert ISBNValidator.is_valid_isbn("9780134686097")
    
    # Invalid ISBNs
    assert not ISBNValidator.is_valid_isbn("1234567890")  # Invalid ISBN-10 checksum
    assert not ISBNValidator.is_valid_isbn("1234567890123")  # Invalid ISBN-13 checksum
    assert not ISBNValidator.is_valid_isbn("123")  # Too short
    assert not ISBNValidator.is_valid_isbn("")  # Empty
    
    # Test normalization
    assert ISBNValidator.normalize_isbn("978-0-13-468-609-7") == "9780134686097"
    assert ISBNValidator.normalize_isbn("0-13-468-604-X") == "013468604X"

def test_text_validation():
    """Test text validation and sanitization."""
    # Valid text
    assert TextValidator.validate_title("Valid Book Title")
    assert TextValidator.validate_author("John Doe")
    
    # Invalid text
    assert not TextValidator.validate_title("")  # Empty
    assert not TextValidator.validate_title("   ")  # Whitespace only
    assert not TextValidator.validate_author("123456")  # Numbers only
    
    # Test sanitization
    dangerous_input = "<script>alert('xss')</script>Title"
    sanitized = TextValidator.sanitize_text(dangerous_input)
    assert "<script>" not in sanitized
    assert "alert" not in sanitized
    assert "Title" in sanitized

def test_error_handling(test_client):
    """Test error handling for various scenarios."""
    headers = {"X-API-Key": "super-secret-key"}
    
    # Test invalid ISBN
    response = test_client.post("/books", json={"isbn": "invalid"}, headers=headers)
    assert response.status_code == 400
    
    # Test missing API key
    response = test_client.post("/books", json={"isbn": "9780134686097"})
    assert response.status_code == 403
    
    # Test invalid API key
    bad_headers = {"X-API-Key": "invalid-key"}
    response = test_client.post("/books", json={"isbn": "9780134686097"}, headers=bad_headers)
    assert response.status_code == 403
    
    # Test getting non-existent book
    response = test_client.get("/books/9999999999999")
    assert response.status_code == 404
    
    # Test deleting non-existent book
    response = test_client.delete("/books/9999999999999", headers=headers)
    assert response.status_code == 404

def test_health_endpoint(test_client):
    """Test health check endpoint."""
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert "total_books" in data

def test_statistics(test_client):
    """Test statistics endpoints."""
    headers = {"X-API-Key": "super-secret-key"}
    
    # Add some books
    books = [
        {"isbn": "9780134686097", "title": "Book 1", "author": "Author A"},
        {"isbn": "9780134686098", "title": "Book 2", "author": "Author A"},
        {"isbn": "9780134686099", "title": "Book 3", "author": "Author B"}
    ]
    
    for book in books:
        response = test_client.post("/books", json=book, headers=headers)
        assert response.status_code == 200
    
    # Test basic stats
    response = test_client.get("/stats")
    assert response.status_code == 200
    stats = response.json()
    assert stats["total_books"] == 3
    assert stats["unique_authors"] == 2
    
    # Test extended stats
    response = test_client.get("/stats/extended")
    assert response.status_code == 200
    extended_stats = response.json()
    assert extended_stats["total_books"] == 3
    assert extended_stats["unique_authors"] == 2
    assert "most_common_author" in extended_stats
    assert "books_by_author" in extended_stats
    assert extended_stats["most_common_author"] == "Author A"
