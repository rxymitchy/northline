import os
from pathlib import Path

_data = Path(__file__).resolve().parent.parent / "data"
_data.mkdir(exist_ok=True)
_db = _data / "test-prospects.db"
# Start every test run from an empty database so free-run counts do not pile up.
_db.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = "sqlite:///" + _db.as_posix()
