from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aar_api import __version__
from aar_api.core.config import get_settings
from aar_api.routers import (
    aar,
    audit,
    dictionaries,
    events,
    exports,
    health,
    integrations,
    llm,
    reports,
)

settings = get_settings()

if settings.environment != "development" and settings.jwt_secret == "change-me-in-production":
    raise RuntimeError("AAR_JWT_SECRET must be set in non-development environments")

app = FastAPI(title=settings.app_name, version=__version__, root_path="/api")

allowed = ["http://localhost:5173", "http://localhost:8080"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(dictionaries.router)
app.include_router(events.router)
app.include_router(reports.router)
app.include_router(aar.router)
app.include_router(llm.router)
app.include_router(exports.router)
app.include_router(integrations.router)
app.include_router(audit.router)
