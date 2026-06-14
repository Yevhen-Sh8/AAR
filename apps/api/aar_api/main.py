from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import JWTError

from aar_api import __version__
from aar_api.core.config import get_settings
from aar_api.core.security import decode_token
from aar_api.routers import (
    aar,
    audit,
    auth,
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

# CORS. The API carries no cookies (auth is header-based JWT), so when the
# allow-list is "*" we can safely echo `*` with credentials disabled — this
# is the bullet-proof setting for a split-origin deploy (web ≠ api host) and
# sidesteps any regex/host-matching fragility. Restrict to explicit origins
# for a hardened deployment by setting AAR_CORS_ORIGINS to real hosts.
origins = settings.cors_origin_list
cors_kwargs: dict = {"allow_methods": ["*"], "allow_headers": ["*"]}
if "*" in origins:
    cors_kwargs["allow_origins"] = ["*"]
    cors_kwargs["allow_credentials"] = False
else:
    cors_kwargs["allow_origins"] = origins
    cors_kwargs["allow_credentials"] = True
    if settings.cors_origin_regex:
        cors_kwargs["allow_origin_regex"] = settings.cors_origin_regex
app.add_middleware(CORSMiddleware, **cors_kwargs)


# ───────────────────────── global auth gate ──────────────────────────────
# Everything is behind login in production, except a small public allow-list.
# In development the gate is disabled so the test-suite and local work stay
# frictionless (matches the dev-bypass in core/rbac.require_role).
_PUBLIC_EXACT = {
    "/", "/auth/login", "/health/live", "/health/ready",
    "/docs", "/redoc", "/openapi.json",
}


def _is_public(path: str) -> bool:
    # Normalise the optional "/api" root_path prefix added by the proxy.
    if path.startswith("/api/"):
        path = path[4:]
    elif path == "/api":
        path = "/"
    return path in _PUBLIC_EXACT or path.startswith("/auth/")


@app.middleware("http")
async def auth_gate(request: Request, call_next):
    if settings.environment == "development" or request.method == "OPTIONS":
        return await call_next(request)
    if _is_public(request.url.path):
        return await call_next(request)
    header = request.headers.get("Authorization", "")
    token = header[7:] if header.startswith("Bearer ") else ""
    if not token:
        return JSONResponse({"detail": "authentication required"}, status_code=401)
    try:
        decode_token(token)
    except JWTError:
        return JSONResponse({"detail": "invalid or expired token"}, status_code=401)
    return await call_next(request)


app.include_router(auth.router)
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
