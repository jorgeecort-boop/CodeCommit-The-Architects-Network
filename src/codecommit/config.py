import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


def _resolve_db_path() -> Path:
    # Prioridad:
    # 1) CODECOMMIT_DB_PATH (ruta directa)
    # 2) DATABASE_URL (solo sqlite:///)
    # 3) fallback local en ./data
    explicit = os.getenv("CODECOMMIT_DB_PATH")
    if explicit:
        return Path(explicit).resolve()

    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url.lower().startswith("sqlite:///"):
        sqlite_path = database_url[len("sqlite:///") :]
        if sqlite_path:
            return Path(sqlite_path).resolve()

    return Path(DATA_DIR / "codecommit.db").resolve()


DB_PATH = _resolve_db_path()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

MEDIA_DIR = Path(os.getenv("CODECOMMIT_MEDIA_DIR", str(DATA_DIR / "media"))).resolve()
MEDIA_DIR.mkdir(exist_ok=True)
HOST = "127.0.0.1"
PORT = 8080
