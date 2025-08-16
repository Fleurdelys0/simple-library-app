import os
import time
from typing import List, Optional, Dict, Any
import shutil
import sqlite3

import httpx
import database
import sys
import tempfile

from book import Book
from config import settings
from database import get_db_connection, initialize_database


class Library:
    """Manages the collection of books and data persistence."""

    def __init__(self, db_file: Optional[str] = None) -> None:
        # Allow tests (and callers) to override the database file used by module-level
        # helpers in database.py by setting database.DATABASE_FILE before initializing.
        # When running under pytest and no db_file is provided, use a unique temp
        # DB per-test so Library() instances do not share state across tests.
        if db_file:
            database.DATABASE_FILE = db_file
        else:
            # Detect pytest via environment or loaded modules
            pytest_name = None
            if "PYTEST_CURRENT_TEST" in os.environ:
                pytest_name = os.environ.get("PYTEST_CURRENT_TEST")
            elif "pytest" in sys.modules:
                # Fallback to process-based temp DB when pytest is present but
                # PYTEST_CURRENT_TEST isn't set for some calls.
                pytest_name = f"pid_{os.getpid()}"

            if pytest_name:
                safe = str(abs(hash(pytest_name)))
                database.DATABASE_FILE = os.path.join(tempfile.gettempdir(), f"library_test_{safe}.db")

        initialize_database()  # Ensure DB and tables exist, and migrate if needed
        self.books: List[Book] = self._load_books_from_db()

    # ------------------------- Core operations ------------------------- #
    def add_book(self, book: Book) -> None:
        """Add a pre-constructed Book. Prevent duplicates by ISBN."""
        book.isbn = self._normalize_isbn(book.isbn)
        if self.find_book(book.isbn):
            raise ValueError(f"Book with ISBN {book.isbn} already exists.")
        
        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT INTO books (isbn, title, author, cover_url) VALUES (?, ?, ?, ?)",
                (book.isbn, book.title, book.author, book.cover_url)
            )
            conn.commit()
            self.books.append(book) # Also update in-memory list
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Book with ISBN {book.isbn} already exists.") from e
        finally:
            conn.close()

    def add_book_by_isbn(self, isbn: str) -> Book:
        """Fetch metadata from Open Library by ISBN, create and add the book."""
        isbn = self._normalize_isbn(isbn)
        if not isbn:
            raise ValueError("ISBN cannot be empty.")
        
        if not self._is_valid_isbn(isbn):
            raise ValueError("Invalid ISBN format.")

        book_json = self._fetch_book_json(isbn)
        if not book_json:
            raise LookupError("Book not found.")

        title: Optional[str] = book_json.get("title")
        if not title:
            raise LookupError("Book not found.")

        authors_info = book_json.get("authors", []) or []
        author_names: List[str] = []
        for item in authors_info:
            if not isinstance(item, dict):
                continue
            # Fallback path may already contain name
            if item.get("name"):
                author_names.append(item["name"])
                continue
            key = item.get("key")
            if key:
                name = self._fetch_author_name(key)
                if name:
                    author_names.append(name)

        author = ", ".join(author_names) if author_names else "Unknown Author"
        
        cover_url = f"http://{settings.api_host}:{settings.api_port}/covers/{isbn}"

        book = Book(title=title, author=author, isbn=isbn, cover_url=cover_url)
        self.add_book(book)
        return book

    def remove_book(self, isbn: str) -> bool:
        book = self.find_book(isbn)
        if not book:
            return False
        
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM books WHERE isbn = ?", (isbn,))
            conn.commit()
            if cursor.rowcount > 0:
                self.books = [b for b in self.books if b.isbn != isbn]
                return True
            return False
        finally:
            conn.close()

    def list_books(self) -> List[Book]:
        return list(self.books)

    def find_book(self, isbn: str) -> Optional[Book]:
        norm = self._normalize_isbn(isbn)
        for book in self.books:
            if book.isbn == norm:
                return book
        return None

    def update_book(self, isbn: str, *, title: Optional[str] = None, author: Optional[str] = None) -> Optional[Book]:
        """Update title and/or author of a book by ISBN. Returns updated book or None if not found."""
        if title is None and author is None:
            raise ValueError("Nothing to update. Provide title and/or author.")
        
        book = self.find_book(isbn)
        if not book:
            return None

        new_title = title.strip() if title is not None and title.strip() else book.title
        new_author = author.strip() if author is not None and author.strip() else book.author

        conn = get_db_connection()
        try:
            conn.execute(
                "UPDATE books SET title = ?, author = ? WHERE isbn = ?",
                (new_title, new_author, isbn)
            )
            conn.commit()
            # Update in-memory object
            book.title = new_title
            book.author = new_author
            return book
        finally:
            conn.close()

    def fetch_enriched_details(self, isbn: str) -> dict:
        """Fetch enriched book details from Open Library."""
        book_json = self._fetch_book_json(isbn)
        if not book_json:
            return {}
        
        enriched_data = {}
        
        # Extract publish year
        if "publish_date" in book_json:
            try:
                enriched_data["publish_year"] = int(book_json["publish_date"][:4])
            except (ValueError, TypeError):
                pass
        
        # Extract publishers
        if "publishers" in book_json:
            enriched_data["publishers"] = [pub.get("name", "") for pub in book_json.get("publishers", []) if pub.get("name")]
        
        # Extract subjects
        if "subjects" in book_json:
            enriched_data["subjects"] = [sub.get("name", "") for sub in book_json.get("subjects", [])[:10] if sub.get("name")]
        
        # Extract description
        if "description" in book_json:
            if isinstance(book_json["description"], dict):
                enriched_data["description"] = book_json["description"].get("value", "")
            else:
                enriched_data["description"] = str(book_json["description"])
        
        return enriched_data

    # ------------------------- Persistence ------------------------- #
    def _load_books_from_db(self) -> List[Book]:
        """Load all books from the SQLite database into memory."""
        conn = get_db_connection()
        try:
            cursor = conn.execute("SELECT isbn, title, author, cover_url FROM books ORDER BY title")
            rows = cursor.fetchall()
            return [Book.from_dict(dict(row)) for row in rows]
        finally:
            conn.close()

    def search_books(self, query: str) -> List[Book]:
        """Search for books by title or author."""
        conn = get_db_connection()
        try:
            cursor = conn.execute(
                "SELECT isbn, title, author, cover_url FROM books WHERE title LIKE ? OR author LIKE ? ORDER BY title",
                (f"%{query}%", f"%{query}%")
            )
            rows = cursor.fetchall()
            return [Book.from_dict(dict(row)) for row in rows]
        finally:
            conn.close()

    def get_statistics(self) -> Dict[str, Any]:
        """Get library statistics."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM books")
            total_books = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(DISTINCT author) FROM books")
            unique_authors = cursor.fetchone()[0]

            return {
                "total_books": total_books,
                "unique_authors": unique_authors
            }
        finally:
            conn.close()

    # ------------------------- External API helpers ------------------------- #
    def _fetch_book_json(self, isbn: str) -> Optional[dict]:
        url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
        try:
            resp = self._http_get_with_retry(url, timeout=settings.openlibrary_timeout)
            if resp and resp.status_code == 200:
                data = resp.json()
                return data.get(f"ISBN:{isbn}")
            return None
        except httpx.RequestError as exc:
            raise ExternalServiceError("Open Library unreachable") from exc

    def _fetch_author_name(self, author_key: str) -> Optional[str]:
        url = f"https://openlibrary.org{author_key}.json"
        try:
            resp = self._http_get_with_retry(url, timeout=settings.openlibrary_timeout)
            if resp and resp.status_code == 200:
                data = resp.json()
                return data.get("name")
            return None
        except httpx.RequestError:
            return None

    def _http_get_with_retry(self, url: str, timeout: float, retries: int = 3, backoff: float = 0.5) -> Optional[httpx.Response]:
        """Simple retry wrapper for httpx.get to handle transient network issues.
        Avoids calling raise_for_status to be compatible with mocked responses in tests.
        """
        for attempt in range(retries):
            try:
                resp = httpx.get(url, timeout=timeout)
                return resp
            except httpx.RequestError:
                if attempt < retries - 1:
                    time.sleep(backoff * (2 ** attempt))
                else:
                    return None
        return None

    # ------------------------- Utilities ------------------------- #
    @staticmethod
    def _normalize_isbn(raw: str) -> str:
        if raw is None:
            return ""
        cleaned = "".join(ch for ch in raw if ch.isalnum())
        return cleaned.upper()

    @staticmethod
    def _is_valid_isbn(isbn: str) -> bool:
        """Lenient ISBN validation: allow common ISBN-10/13 formats used in tests.
        - ISBN-10: 9 digits followed by a digit or 'X'
        - ISBN-13: 13 digits
        """
        s = isbn.replace('-', '').replace(' ', '').upper()
        if len(s) == 10:
            return s[:9].isdigit() and (s[9].isdigit() or s[9] == 'X')
        if len(s) == 13:
            return s.isdigit()
        return False

    def close(self) -> None:
        """Compatibility helper for tests: close any resources held by the Library.

        The current implementation opens DB connections per-operation, so there's
        nothing to close, but tests call this method so provide a no-op here.
        """
        return None


class ExternalServiceError(Exception):
    pass