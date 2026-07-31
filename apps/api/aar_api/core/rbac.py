"""Role-based access control via JWT bearer tokens.

Routes opt-in by adding `Depends(require_role(Role.ADMIN, Role.MANAGER, ...))`.
In dev/test mode (AAR_ENVIRONMENT=development), the dependency is permissive
to keep local development and the existing test suite frictionless. In any
non-dev environment a valid Bearer token whose `role` claim matches one of
the allowed roles is required.
"""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError as JWTError

from aar_api.core.config import get_settings
from aar_api.core.security import decode_token
from aar_api.models.user import Role

_bearer = HTTPBearer(auto_error=False)


def require_role(*allowed: Role):
    async def _dep(
        creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    ) -> dict:
        settings = get_settings()
        if settings.environment == "development":
            return {"sub": "dev", "role": Role.ADMIN.value, "dev_bypass": True}
        if creds is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="bearer token required",
            )
        try:
            claims = decode_token(creds.credentials)
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"invalid token: {e}",
            ) from e
        role = claims.get("role")
        if role not in {r.value for r in allowed}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"role '{role}' not permitted",
            )
        return claims

    return _dep


async def optional_claims(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict | None:
    """Decode the bearer token if there is a valid one; otherwise return None.

    DELIBERATE ASYMMETRY with `require_role`: this helper has NO dev-bypass.
    `require_role` short-circuits to ADMIN whenever the environment is
    "development" — which is also the test environment — so reusing it to
    decide *privacy* questions would both reveal identities in dev and make
    the redaction path untestable. A privacy control must fail closed: no
    token, an expired token or a malformed token all yield None, and every
    caller treats None as "not privileged". Do not "unify" this with
    require_role; doing so re-opens the anonymity leak.
    """
    if creds is None:
        return None
    try:
        return decode_token(creds.credentials)
    except JWTError:
        return None


def has_role(claims: dict | None, *allowed: Role) -> bool:
    """True when the (already decoded) claims carry one of `allowed`."""
    if not claims:
        return False
    return claims.get("role") in {r.value for r in allowed}
