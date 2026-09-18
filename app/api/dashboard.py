"""Dashboard router serving UI assets and landing pages."""

from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

dashboard_router = APIRouter(tags=["Dashboard"])
DASHBOARD_DIR = Path(__file__).resolve().parent.parent.parent / "dashboard"


@dashboard_router.get("/", response_class=HTMLResponse)
@dashboard_router.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard():
    """Serves the main Gateway & Firewall monitoring dashboard UI."""
    index_file = DASHBOARD_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)
