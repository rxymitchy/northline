from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api import router
from app.config import settings
from app.db import init_db

Path("data").mkdir(exist_ok=True)
init_db()

app = FastAPI(title="Find Clients Agent", version="0.1.0")
origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "search_provider": settings.search_provider,
        "email_sending_enabled": settings.email_sending_enabled,
        "openai_configured": bool(settings.openai_api_key),
    }


@app.get("/")
def dashboard():
    return FileResponse(STATIC_DIR / "index.html")
