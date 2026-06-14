"""Authentication: password login → JWT, plus the current-user probe.

The login route is intentionally public (see the auth gate in main.py). Tokens
embed the user's `role` claim so `require_role(...)` dependencies and the global
auth middleware can authorise without a DB round-trip.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.core.config import get_settings
from aar_api.core.db import get_session
from aar_api.core.security import create_access_token, decode_token, verify_password
from aar_api.models.user import User
from aar_api.schemas.auth import LoginRequest, MeResponse, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

_bearer = HTTPBearer(auto_error=False)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    user = await session.scalar(
        select(User).where(User.email == payload.email.strip().lower())
    )
    if user is None or not verify_password(payload.password, user.hashed_password):
        # Same message for both cases — don't leak which emails exist.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="невірний email або пароль",
        )
    token = create_access_token(
        subject=user.email, extra={"role": user.role.value, "uid": user.id}
    )
    return TokenResponse(
        access_token=token, expires_minutes=get_settings().jwt_expires_minutes
    )


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: AsyncSession = Depends(get_session),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bearer token required")
    try:
        claims = decode_token(creds.credentials)
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}") from e
    user = await session.scalar(select(User).where(User.email == claims.get("sub")))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user no longer exists")
    return user


@router.get("/me", response_model=MeResponse)
async def me(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user
