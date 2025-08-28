import sqlite3
import json
import os
import sys
from typing import List, Dict, Any

import tempfile
from dotenv import load_dotenv

# .env'den ortam değişkenlerinin okunmadan önce yüklendiğinden emin olun.
# Bu, modüllerin, load_dotenv() çağrılmadan önce os.environ'u okuyacak bir sırada içe aktarıldığı sorunları önler (ör. library -> database -> config).
load_dotenv()

# Varsayılan veritabanı dosyası.
# Öncelik:
# 1) LIBRARY_DB_FILE (yeni, açık geçersiz kılma)
# 2) LIBRARY_DATA_FILE (config.py/.env tarafından kullanılan eski ortam)
# 3) İşlem başına geçici dosya (OneDrive kilit sorunlarını önlemek için güvenli geri dönüş)
DATABASE_FILE = (
    os.environ.get("LIBRARY_DB_FILE")
    or os.environ.get("LIBRARY_DATA_FILE")
    or os.path.join(tempfile.gettempdir(), f"library_{os.getpid()}.db")
)
JSON_FILE = "library.json"

# Daha iyi performans için bağlantı havuzu
_connection_pool = None
_pool_lock = None

def _initialize_connection_pool():
    """Daha iyi performans için bağlantı havuzunu başlat."""
    global _connection_pool, _pool_lock
    import threading
    from contextlib import contextmanager
    import queue
    
    if _connection_pool is None:
        _pool_lock = threading.Lock()
        # Eşzamanlı erişim için 5 bağlantılık bir havuz oluştur
        _connection_pool = queue.Queue(maxsize=5)
        for _ in range(5):
            conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            # Daha iyi eşzamanlı erişim için WAL modunu etkinleştir
            conn.execute("PRAGMA journal_mode=WAL;")
            # Performans için SQLite ayarlarını optimize et
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA cache_size=-64000;")  # 64MB önbellek
            conn.execute("PRAGMA temp_store=MEMORY;")
            conn.execute("PRAGMA mmap_size=268435456;")  # 256MB mmap
            _connection_pool.put(conn)

def get_db_connection() -> sqlite3.Connection:
    """Bağlantı havuzu ile SQLite veritabanına bir bağlantı kurar."""
    # Testler için karmaşıklığı önlemek için basit bağlantı kullanın
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        conn = sqlite3.connect(DATABASE_FILE)
        conn.row_factory = sqlite3.Row
        return conn
    
    global _connection_pool, _pool_lock
    if _connection_pool is None:
        _initialize_connection_pool()
    
    try:
        # Havuzdan bir bağlantı almayı deneyin (engellemesiz)
        return _connection_pool.get_nowait()
    except:
        # Havuz boşsa, yeni bir optimize edilmiş bağlantı oluşturun
        conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA cache_size=-64000;")
        conn.execute("PRAGMA temp_store=MEMORY;")
        return conn

def return_connection_to_pool(conn: sqlite3.Connection):
    """Yeniden kullanım için havuza bir bağlantı döndürün."""
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        conn.close()
        return
    
    global _connection_pool
    if _connection_pool is not None:
        try:
            _connection_pool.put_nowait(conn)
        except:
            # Havuz dolu, bağlantıyı kapat
            conn.close()

def create_tables() -> None:
    """Veritabanında mevcut değilse gerekli tabloları oluşturur."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS books (
            isbn TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            cover_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            publish_year INTEGER
        )
    """)
    
    # Puanlar ve yorumlar için inceleme tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            isbn TEXT NOT NULL,
            user_name TEXT NOT NULL,
            rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (isbn) REFERENCES books(isbn) ON DELETE CASCADE
        )
    """)
    
    # Kategoriler/raflar için etiket tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            color TEXT DEFAULT '#3B82F6',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Kitap-Etiket ilişki tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS book_tags (
            isbn TEXT NOT NULL,
            tag_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (isbn, tag_id),
            FOREIGN KEY (isbn) REFERENCES books(isbn) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        )
    """)
    
    # API kullanım izleme tabloları
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_name TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            success BOOLEAN NOT NULL,
            response_time_ms INTEGER,
            characters_used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_usage_stats (
            id INTEGER PRIMARY KEY,
            google_books_daily_calls INTEGER DEFAULT 0,
            hugging_face_monthly_chars INTEGER DEFAULT 0,
            last_reset_date TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Daha iyi performans için dizinler oluştur
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reviews_isbn ON reviews(isbn)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reviews_rating ON reviews(rating)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_book_tags_isbn ON book_tags(isbn)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_book_tags_tag_id ON book_tags(tag_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_usage_logs_api_name ON api_usage_logs(api_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_usage_logs_created_at ON api_usage_logs(created_at)")
    
    
    # Sütunların var olup olmadığını kontrol edin, yoksa ekleyin (geçiş için)
    cursor.execute("PRAGMA table_info(books)")
    columns = [column[1] for column in cursor.fetchall()]
    
    # Orijinal sütunlar
    if 'created_at' not in columns:
        # SQLite, ALTER TABLE aracılığıyla sabit olmayan bir varsayılanla sütun eklemeye izin vermez.
        # Bu yüzden sütunu varsayılan olmadan ekler ve ardından değerleri geri doldururuz.
        cursor.execute("ALTER TABLE books ADD COLUMN created_at TIMESTAMP")
        cursor.execute("UPDATE books SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
    if 'publish_year' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN publish_year INTEGER")
    
    # Google Books API sütunları
    if 'page_count' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN page_count INTEGER")
    if 'categories' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN categories TEXT")  # JSON dizisi
    if 'published_date' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN published_date TEXT")
    if 'publisher' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN publisher TEXT")
    if 'language' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN language TEXT DEFAULT 'tr'")
    if 'description' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN description TEXT")
    if 'google_rating' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN google_rating REAL")
    if 'google_rating_count' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN google_rating_count INTEGER")
    
    # AI tarafından oluşturulan sütunlar
    if 'ai_summary' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN ai_summary TEXT")
    if 'ai_summary_generated_at' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN ai_summary_generated_at TIMESTAMP")
    if 'sentiment_score' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN sentiment_score REAL")
    if 'data_sources' not in columns:
        cursor.execute("ALTER TABLE books ADD COLUMN data_sources TEXT")  # JSON dizisi
    
    # Varsayılan etiketler yoksa ekle
    default_tags = [
        ('Okunacaklar', '#10B981'),
        ('Okunanlar', '#06B6D4'),
        ('Favoriler', '#EF4444'),
        ('2024 Listesi', '#8B5CF6'),
        ('Tekrar Oku', '#F59E0B')
    ]
    
    for tag_name, color in default_tags:
        cursor.execute("INSERT OR IGNORE INTO tags (name, color) VALUES (?, ?)", (tag_name, color))
    
    # "Okunanlar" etiketinin, zaten var olsa bile güncellenmiş turkuaz rengini kullandığından emin olun
    cursor.execute("UPDATE tags SET color = ? WHERE name = ?", ('#06B6D4', 'Okunanlar'))
    
    # Kitaplar tablosu için ek performans dizinleri (sütunlar eklendikten sonra)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_books_title ON books(title)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_books_author ON books(author)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_books_created_at ON books(created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_books_title_author ON books(title, author)")
    
    # Dizin oluşturmadan önce published_date sütununun var olup olmadığını kontrol edin
    cursor.execute("PRAGMA table_info(books)")
    updated_columns = [column[1] for column in cursor.fetchall()]
    if 'published_date' in updated_columns:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_books_published_date ON books(published_date)")
    if 'language' in updated_columns:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_books_language ON books(language)")
    
    # Arama optimizasyonu için bileşik dizinler
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reviews_isbn_rating ON reviews(isbn, rating)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_usage_stats_date ON api_usage_logs(created_at DESC)")
    
    conn.commit()
    conn.close()

def migrate_from_json() -> None:
    """Eski library.json'dan verileri SQLite veritabanına taşır.
    
    Bu tek seferlik bir işlemdir. Devam etmeden önce veritabanının boş olup olmadığını
    ve JSON dosyasının var olup olmadığını kontrol eder.
    """
    # Testler sırasında, veritabanının boş başlaması için tohum verilerini otomatik olarak taşımaktan kaçının.
    # Sağlamlık için pytest'i ortam veya yüklenmiş modüller aracılığıyla tespit edin.
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Kitaplar tablosunun boş olup olmadığını kontrol edin
    cursor.execute("SELECT COUNT(*) FROM books")
    book_count = cursor.fetchone()[0]
    
    if book_count > 0:
        conn.close()
        return # Veritabanında zaten veri var, taşıma gerekmez

    if not os.path.exists(JSON_FILE):
        conn.close()
        return # JSON dosyası mevcut değil

    print("Veriler library.json'dan SQLite veritabanına taşınıyor...")
    
    try:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            data: List[Dict[str, Any]] = json.load(f)
        
        books_to_insert = []
        for item in data:
            # Temel doğrulama
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
        print(f"{len(books_to_insert)} kitap başarıyla taşındı.")

    except (json.JSONDecodeError, IOError) as e:
        print(f"{JSON_FILE} okunurken veya ayrıştırılırken hata oluştu: {e}")
    finally:
        conn.close()

def initialize_database():
    """Veritabanını başlatır, gerekirse tabloları oluşturur ve verileri taşır."""
    create_tables()
    migrate_from_json()