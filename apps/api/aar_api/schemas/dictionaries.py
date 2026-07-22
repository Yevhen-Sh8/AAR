from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from aar_api.models.dictionaries import Zone


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- Outputs -------------------------------------------------------------

class ItemTypeOut(_Base):
    id: int
    code: str
    name_uk: str
    unit_cost_usd: Decimal | None = None


class OperatorOut(_Base):
    id: int
    code: str
    name_uk: str


class ReasonOut(_Base):
    id: int
    code: str
    name_uk: str
    zone: Zone


# ---- Inputs (create) -----------------------------------------------------
# `code` is the stable identifier used in imports and external mappings, so it
# is required on create but NOT editable on update (see *Update schemas).

def _clean_code(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("code must not be empty")
    return v


def _clean_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("name_uk must not be empty")
    return v


class ItemTypeIn(BaseModel):
    code: str
    name_uk: str
    unit_cost_usd: Decimal | None = None

    _vc = field_validator("code")(_clean_code)
    _vn = field_validator("name_uk")(_clean_name)


class OperatorIn(BaseModel):
    code: str
    name_uk: str

    _vc = field_validator("code")(_clean_code)
    _vn = field_validator("name_uk")(_clean_name)


class ReasonIn(BaseModel):
    code: str
    name_uk: str
    zone: Zone

    _vc = field_validator("code")(_clean_code)
    _vn = field_validator("name_uk")(_clean_name)


# ---- Inputs (update) -----------------------------------------------------
# Partial updates; `code` is intentionally immutable. The router applies only
# the fields actually sent (model_dump(exclude_unset=True)), so omitting a
# field leaves it unchanged while explicitly sending null clears it.

class ItemTypeUpdate(BaseModel):
    name_uk: str | None = None
    unit_cost_usd: Decimal | None = None

    _vn = field_validator("name_uk")(lambda v: v if v is None else _clean_name(v))


class OperatorUpdate(BaseModel):
    name_uk: str | None = None

    _vn = field_validator("name_uk")(lambda v: v if v is None else _clean_name(v))


class ReasonUpdate(BaseModel):
    name_uk: str | None = None
    zone: Zone | None = None

    _vn = field_validator("name_uk")(lambda v: v if v is None else _clean_name(v))
