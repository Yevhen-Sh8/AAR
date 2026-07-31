"""Schemas for the people directory (Wave 11).

`hashed_password` never appears in any schema here — not on input, not on
output. Setting a password goes through the dedicated
`POST /people/{id}/set-password` route.

`email` is a plain `str` with a minimal shape check rather than pydantic's
`EmailStr`: the project does not depend on `email-validator`, and the login
lookup only ever needs a normalised, lower-cased string.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from aar_api.models.user import ParticipantFunction, Role


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _clean_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("full_name must not be empty")
    return v


def _clean_email(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip().lower()
    if not v:
        return None
    local, _, domain = v.partition("@")
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ValueError("невірний формат email")
    return v


def _clean_optional_str(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


class PersonOut(_Base):
    id: int
    full_name: str
    callsign: str | None
    email: str | None
    role: Role
    operator_id: int | None
    function: ParticipantFunction | None
    is_active: bool
    can_login: bool
    created_at: datetime


class PersonIn(BaseModel):
    """Create a person. `password` (admin only) makes them a login account."""

    full_name: str
    callsign: str | None = None
    email: str | None = None
    role: Role = Role.PARTICIPANT
    operator_id: int | None = None
    function: ParticipantFunction | None = None
    password: str | None = Field(default=None, min_length=8)

    _vn = field_validator("full_name")(_clean_name)
    _ve = field_validator("email")(_clean_email)
    _vc = field_validator("callsign")(_clean_optional_str)


class PersonUpdate(BaseModel):
    """Partial update — only the fields actually sent are applied."""

    full_name: str | None = None
    callsign: str | None = None
    email: str | None = None
    role: Role | None = None
    operator_id: int | None = None
    function: ParticipantFunction | None = None
    is_active: bool | None = None

    _vn = field_validator("full_name")(lambda v: v if v is None else _clean_name(v))
    _ve = field_validator("email")(_clean_email)
    _vc = field_validator("callsign")(_clean_optional_str)


class SetPasswordIn(BaseModel):
    password: str = Field(min_length=8)
