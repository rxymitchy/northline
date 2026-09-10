from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api import router
from app.config import settings
from app.db import init_db
from app.emailer import sending_outbound_allowed, smtp_ready

Path("data").mkdir(exist_ok=True)
init_db()

app = FastAPI(title="Northline", version="0.2.0")
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
        "outbound_send_enabled": settings.outbound_send_enabled,
        "smtp_configured": smtp_ready(),
        "outbound_will_send": sending_outbound_allowed(),
        "openai_configured": bool(settings.openai_api_key),
    }


@app.get("/")
def dashboard():
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/admin")
def admin_page():
    return FileResponse(
        STATIC_DIR / "admin.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )
