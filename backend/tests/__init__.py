import os
from pathlib import Path

_data = Path(__file__).resolve().parent.parent / "data"
_data.mkdir(exist_ok=True)
os.environ["DATABASE_URL"] = "sqlite:///" + (_data / "test-prospects.db").as_posix()
