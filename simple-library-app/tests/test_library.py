import pytest
import os
import sqlite3

from library import Library
from book import Book
from database import DATABASE_FILE, get_db_connection, initialize_database

# Fixture to ensure a clean database for each test
@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(DATABASE_FILE):
        os.remove(DATABASE_FILE)
    initialize_database() # Ensure tables are created
    lib = Library()
    yield lib
    lib.close()
    if os.path.exists(DATABASE_FILE):
        os.remove(DATABASE_FILE)

def test_add_list_and_find(lib):
    assert lib.list_books() == []

    book = Book("Ulysses", "James Joyce", "9780199535675")
    lib.add_book(book)

    assert lib.find_book(book.isbn) is not None
    assert len(lib.list_books()) == 1
    assert lib.list_books()[0].title == "Ulysses" # Check title directly

def test_add_duplicate_isbn():
    lib = Library()
    book1 = Book("Test Book", "Test Author", "1234567890")
    lib.add_book(book1)

    with pytest.raises(ValueError, match="Book with ISBN 1234567890 already exists."):
        lib.add_book(book1) # Try adding the same book again

    assert len(lib.list_books()) == 1 # Ensure no duplicate was added

def test_persistence():
    lib = Library()
    lib.add_book(Book("Sapiens", "Yuval Noah Harari", "9780099590088"))

    # New instance should read persisted data from SQLite
    lib2 = Library()
    assert len(lib2.list_books()) == 1
    assert lib2.find_book("9780099590088").title == "Sapiens"

def test_remove():
    lib = Library()
    lib.add_book(Book("Test", "Author", "123"))
    assert lib.remove_book("123") is True
    assert lib.remove_book("123") is False # Should return False if not found

def test_update_book():
    lib = Library()
    book = Book("Old Title", "Old Author", "1112223334")
    lib.add_book(book)

    updated_book = lib.update_book("1112223334", title="New Title", author="New Author")
    assert updated_book is not None
    assert updated_book.title == "New Title"
    assert updated_book.author == "New Author"

    # Verify persistence
    lib2 = Library()
    found_book = lib2.find_book("1112223334")
    assert found_book.title == "New Title"
    assert found_book.author == "New Author"

def test_update_book_partial():
    lib = Library()
    book = Book("Original Title", "Original Author", "4445556667")
    lib.add_book(book)

    updated_book = lib.update_book("4445556667", title="Only Title Changed")
    assert updated_book.title == "Only Title Changed"
    assert updated_book.author == "Original Author" # Author should remain unchanged

    updated_book = lib.update_book("4445556667", author="Only Author Changed")
    assert updated_book.title == "Only Title Changed" # Title should remain unchanged
    assert updated_book.author == "Only Author Changed"

def test_update_book_not_found():
    lib = Library()
    updated_book = lib.update_book("nonexistent", title="New Title")
    assert updated_book is None

def test_add_book_by_isbn_success(monkeypatch):
    lib = Library()

    class FakeResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json = json_data

        def json(self):
            return self._json

    def fake_get(url, timeout=10):
        if url.endswith("/api/books?bibkeys=ISBN:9780321765723&format=json&jscmd=data"):
            return FakeResponse(200, {"ISBN:9780321765723": {"title": "Effective C++", "authors": [{"key": "/authors/OL12345A"}]}})
        if url.endswith("/authors/OL12345A.json"):
            return FakeResponse(200, {"name": "Scott Meyers"})
        return FakeResponse(404, {})

    monkeypatch.setattr("library.httpx.get", fake_get)
    book = lib.add_book_by_isbn("9780321765723")
    assert book.title == "Effective C++"
    assert "Scott Meyers" in book.author
    assert lib.find_book("9780321765723") is not None

def test_add_book_by_isbn_not_found(monkeypatch):
    lib = Library()

    class FakeResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json = json_data

        def json(self):
            return self._json

    def fake_get(url, timeout=10):
        return FakeResponse(404, {})

    monkeypatch.setattr("library.httpx.get", fake_get)
    with pytest.raises(LookupError):
        lib.add_book_by_isbn("0000000000")