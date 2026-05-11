from pydantic import BaseModel, ConfigDict

from aar_api.models.dictionaries import Zone


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ItemTypeOut(_Base):
    id: int
    code: str
    name_uk: str


class OperatorOut(_Base):
    id: int
    code: str
    name_uk: str


class ReasonOut(_Base):
    id: int
    code: str
    name_uk: str
    zone: Zone
