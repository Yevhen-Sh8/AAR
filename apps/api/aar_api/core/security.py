from datetime import UTC, datetime, timedelta
from typing import Any

from jose import jwt
from passlib.context import CryptContext

from aar_api.core.config import get_settings

# pbkdf2_sha256 is pure-Python (no native bcrypt backend) — avoids the
# passlib↔bcrypt 4.x incompatibility and runs identically everywhere.
_pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    s = get_settings()
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": datetime.now(UTC) + timedelta(minutes=s.jwt_expires_minutes),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    s = get_settings()
    return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
