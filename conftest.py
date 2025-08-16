import os
import tempfile
import pytest

from library import Library
from database import DATABASE_FILE

@pytest.fixture
def lib(tmp_path, request):
    # Create a unique DB file per-test
    db_file = str(tmp_path / f"test_{request.node.name}.db")
    # Ensure the Library uses this DB file
    lib = Library(db_file=db_file)
    yield lib
    try:
        lib.close()
    except Exception:
        pass
    if os.path.exists(db_file):
        os.remove(db_file)
