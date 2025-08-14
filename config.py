import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    data_file: str = os.getenv("LIBRARY_DATA_FILE", "library.db") # Changed default to .db
    openlibrary_timeout: float = float(os.getenv("OPENLIBRARY_TIMEOUT", "10"))
    api_host: str = os.getenv("API_HOST", "127.0.0.1")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    api_key: str = os.getenv("API_KEY", "super-secret-key")


settings = Settings()


