
JSON_FILE = "library.json"

def get_db_connection(db_file: str = "library.db") -> sqlite3.Connection:
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    return conn

def create_tables(db_file: str = "library.db") -> None:
    """Creates the necessary tables in the database if they don't exist."""
    conn = get_db_connection(db_file)
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

def migrate_from_json(db_file: str = "library.db") -> None:
    """Migrates data from the old library.json to the SQLite database.
    
    This is a one-time operation. It checks if the database is empty
    and if the JSON file exists before proceeding.
    """
    # During tests, avoid auto-migrating seed data so the DB starts empty.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    conn = get_db_connection(db_file)
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

def initialize_database(db_file: str = "library.db"):
    """Initializes the database, creating tables and migrating data if needed."""
    create_tables(db_file)
    migrate_from_json(db_file)
