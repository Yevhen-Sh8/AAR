from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aar_api import __version__
from aar_api.core.config import get_settings
from aar_api.routers import (
    aar,
    audit,
    context,
    dictionaries,
    events,
    exports,
    health,
    integrations,
    learning,
    llm,
    reports,
)

settings = get_settings()

if settings.environment != "development" and settings.jwt_secret == "change-me-in-production":
    raise RuntimeError("AAR_JWT_SECRET must be set in non-development environments")

app = FastAPI(title=settings.app_name, version=__version__, root_path="/api")

cors_kwargs: dict = {
    "allow_origins": settings.cors_origin_list,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if settings.cors_origin_regex:
    cors_kwargs["allow_origin_regex"] = settings.cors_origin_regex
app.add_middleware(CORSMiddleware, **cors_kwargs)

app.include_router(health.router)
app.include_router(dictionaries.router)
app.include_router(events.router)
app.include_router(reports.router)
app.include_router(aar.router)
app.include_router(llm.router)
app.include_router(exports.router)
app.include_router(integrations.router)
app.include_router(audit.router)
app.include_router(context.router)
app.include_router(learning.router)
