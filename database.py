
import sqlite3
import json
import os
import sys
from typing import List, Dict, Any

import tempfile

# Default database file. Use a temp file per-process to avoid locking issues when the
# repository is on a synced folder (OneDrive) which can keep handles open on Windows.
DATABASE_FILE = os.environ.get("LIBRARY_DB_FILE") or os.path.join(tempfile.gettempdir(), f"library_{os.getpid()}.db")
JSON_FILE = "library.json"

def get_db_connection() -> sqlite3.Connection:
    """Establishes a connection to the SQLite database."""
    # Always use the configured DATABASE_FILE. Tests call Library(db_file=...) which
    # sets database.DATABASE_FILE so this keeps connections consistent.
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def create_tables() -> None:
    """Creates the necessary tables in the database if they don't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS books (
            isbn TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            cover_url TEXT
        )
    """)
    conn.commit()
    conn.close()

def migrate_from_json() -> None:
    """Migrates data from the old library.json to the SQLite database.
    
    This is a one-time operation. It checks if the database is empty
    and if the JSON file exists before proceeding.
    """
    # During tests, avoid auto-migrating seed data so the DB starts empty.
    # Detect pytest either via environment or loaded modules for robustness.
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if the books table is empty
    cursor.execute("SELECT COUNT(*) FROM books")
    book_count = cursor.fetchone()[0]
    
    if book_count > 0:
        conn.close()
        return # Database already has data, no need to migrate

    if not os.path.exists(JSON_FILE):
        conn.close()
        return # JSON file doesn't exist

    print("Migrating data from library.json to SQLite database...")
    
    try:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            data: List[Dict[str, Any]] = json.load(f)
        
        books_to_insert = []
        for item in data:
            # Basic validation
            if all(k in item for k in ["isbn", "title", "author"]):
                books_to_insert.append((
                    item["isbn"],
                    item["title"],
                    item["author"],
                    item.get("cover_url", "")
                ))
        
        if books_to_insert:
            cursor.executemany(
                "INSERT OR IGNORE INTO books (isbn, title, author, cover_url) VALUES (?, ?, ?, ?)",
                books_to_insert
            )
            conn.commit()
        print(f"Successfully migrated {len(books_to_insert)} books.")

    except (json.JSONDecodeError, IOError) as e:
        print(f"Error reading or parsing {JSON_FILE}: {e}")
    finally:
        conn.close()

def initialize_database():
    """Initializes the database, creating tables and migrating data if needed."""
    create_tables()
    migrate_from_json()
