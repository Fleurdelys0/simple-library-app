import os
import tempfile
import pytest

from src.library import Library
from src.database import DATABASE_FILE

@pytest.fixture
def lib(tmp_path, request):
    # Her test için benzersiz bir veritabanı dosyası oluştur
    db_file = str(tmp_path / f"test_{request.node.name}.db")
    # Kütüphanenin bu veritabanı dosyasını kullandığından emin ol
    lib = Library(db_file=db_file)
    yield lib
    try:
        lib.close()
    except Exception:
        pass
    if os.path.exists(db_file):
        os.remove(db_file)