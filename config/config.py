import os
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    # API Ayarları
    api_host: str = os.getenv("API_HOST", "127.0.0.1")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    api_key: str = os.getenv("API_KEY", "super-secret-key")
    
    # Veritabanı Ayarları
    database_url: str = os.getenv(
        "DATABASE_URL", 
        "postgresql://library_user:library_pass@localhost:5432/library_db"
    )
    database_pool_size: int = int(os.getenv("DATABASE_POOL_SIZE", "20"))
    database_max_overflow: int = int(os.getenv("DATABASE_MAX_OVERFLOW", "40"))
    data_file: str = os.getenv("LIBRARY_DATA_FILE", "library.db")  # Eski SQLite
    
    # Redis Önbellek Ayarları
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_db: int = int(os.getenv("REDIS_DB", "0"))
    redis_password: Optional[str] = os.getenv("REDIS_PASSWORD")
    cache_ttl: int = int(os.getenv("CACHE_TTL", "300"))  # 5 dakika varsayılan
    
    # Elasticsearch Ayarları
    elasticsearch_host: str = os.getenv("ELASTICSEARCH_HOST", "localhost")
    elasticsearch_port: int = int(os.getenv("ELASTICSEARCH_PORT", "9200"))
    elasticsearch_index: str = os.getenv("ELASTICSEARCH_INDEX", "library_books")
    
    # Harici API Ayarları
    openlibrary_timeout: float = float(os.getenv("OPENLIBRARY_TIMEOUT", "10"))
    
    # Google Books API Ayarları
    google_books_api_key: Optional[str] = os.getenv("GOOGLE_BOOKS_API_KEY")
    google_books_daily_limit: int = int(os.getenv("GOOGLE_BOOKS_DAILY_LIMIT", "1000"))
    google_books_timeout: float = float(os.getenv("GOOGLE_BOOKS_TIMEOUT", "10"))
    
    # Hugging Face API Ayarları
    hugging_face_api_key: Optional[str] = os.getenv("HUGGING_FACE_API_KEY")
    hugging_face_monthly_limit: int = int(os.getenv("HUGGING_FACE_MONTHLY_LIMIT", "30000"))
    hugging_face_timeout: float = float(os.getenv("HUGGING_FACE_TIMEOUT", "15"))
    
    # Eski API anahtarları
    goodreads_api_key: Optional[str] = os.getenv("GOODREADS_API_KEY")
    
    # E-posta Ayarları
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: Optional[str] = os.getenv("SMTP_USERNAME")
    smtp_password: Optional[str] = os.getenv("SMTP_PASSWORD")
    smtp_from_email: str = os.getenv("SMTP_FROM_EMAIL", "noreply@library.com")
    smtp_from_name: str = os.getenv("SMTP_FROM_NAME", "Library System")
    
    # Güvenlik Ayarları
    secret_key: str = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", secret_key)
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_expiration_minutes: int = int(os.getenv("JWT_EXPIRATION_MINUTES", "10080"))  # 7 gün
    
    # Uygulama Ayarları
    app_name: str = os.getenv("APP_NAME", "Kütüphane Yönetim Sistemi")
    app_version: str = os.getenv("APP_VERSION", "2.0.0")
    debug: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
    environment: str = os.getenv("ENVIRONMENT", "development")
    
    # Sayfalama Ayarları
    default_page_size: int = int(os.getenv("DEFAULT_PAGE_SIZE", "20"))
    max_page_size: int = int(os.getenv("MAX_PAGE_SIZE", "100"))
    
    # Yükleme Ayarları
    max_upload_size: int = int(os.getenv("MAX_UPLOAD_SIZE", "10485760"))  # 10MB
    allowed_image_extensions: list = field(default_factory=lambda: [".jpg", ".jpeg", ".png", ".gif", ".webp"])
    
    # İzleme Ayarları
    sentry_dsn: Optional[str] = os.getenv("SENTRY_DSN")
    prometheus_enabled: bool = os.getenv("PROMETHEUS_ENABLED", "False").lower() in ("true", "1", "yes")
    
    # Özellik Bayrakları
    enable_social_features: bool = os.getenv("ENABLE_SOCIAL_FEATURES", "True").lower() in ("true", "1", "yes")
    enable_recommendations: bool = os.getenv("ENABLE_RECOMMENDATIONS", "True").lower() in ("true", "1", "yes")
    enable_email_notifications: bool = os.getenv("ENABLE_EMAIL_NOTIFICATIONS", "False").lower() in ("true", "1", "yes")
    enable_barcode_scanner: bool = os.getenv("ENABLE_BARCODE_SCANNER", "True").lower() in ("true", "1", "yes")
    
    # API Özellik Bayrakları
    enable_google_books: bool = os.getenv("ENABLE_GOOGLE_BOOKS", "True").lower() in ("true", "1", "yes")
    enable_ai_features: bool = os.getenv("ENABLE_AI_FEATURES", "True").lower() in ("true", "1", "yes")
    enable_auto_summarization: bool = os.getenv("ENABLE_AUTO_SUMMARIZATION", "True").lower() in ("true", "1", "yes")
    enable_sentiment_analysis: bool = os.getenv("ENABLE_SENTIMENT_ANALYSIS", "True").lower() in ("true", "1", "yes")
    # AI özet tercih edilen dil (ör. 'tr', 'en')
    ai_summary_language: str = os.getenv("AI_SUMMARY_LANGUAGE", "tr")


settings = Settings()