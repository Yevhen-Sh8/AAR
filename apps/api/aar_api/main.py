import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import JWTError

from aar_api import __version__
from aar_api.core.config import get_settings
from aar_api.core.security import decode_token
from aar_api.routers import (
    aar,
    admin,
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

logger = logging.getLogger("aar_api")

settings = get_settings()

if settings.environment != "development" and settings.jwt_secret == "change-me-in-production":
    raise RuntimeError("AAR_JWT_SECRET must be set in non-development environments")

if settings.environment != "development" and settings.admin_password == "aar-admin-2026":
    # Soft warning, not a hard failure — "hardening without blocking" per
    # Wave 5 scope. The password is still usable; this just nudges the
    # operator toward changing it via the hosting dashboard.
    logger.warning(
        "AAR_ADMIN_PASSWORD is still the hardcoded default — change it in "
        "your hosting dashboard before real use (see docs/DEPLOY.md)."
    )

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


# ───────────────────────── security headers ──────────────────────────────
# Applied to every response, including error responses from the auth gate.
# CSP is looser on the interactive-docs paths (Swagger UI pulls its bundle
# from a CDN); everywhere else it's a strict same-origin default.
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}
_DOCS_PATHS = {"/docs", "/redoc", "/openapi.json"}
_DOCS_CSP = (
    "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; connect-src 'self'"
)
_DEFAULT_CSP = "default-src 'self'; base-uri 'self'; frame-ancestors 'none'"


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for key, value in _SECURITY_HEADERS.items():
        response.headers[key] = value
    path = request.url.path
    if path.startswith("/api/"):
        path = path[4:]
    elif path == "/api":
        path = "/"
    response.headers["Content-Security-Policy"] = (
        _DOCS_CSP if path in _DOCS_PATHS else _DEFAULT_CSP
    )
    return response


app.include_router(auth.router)
app.include_router(admin.router)
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
