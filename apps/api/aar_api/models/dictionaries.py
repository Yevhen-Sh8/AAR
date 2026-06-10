from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Enum, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from aar_api.core.db import Base


class Zone(StrEnum):
    OPERATOR = "operator"
    MANUFACTURER = "manufacturer"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class ItemType(Base):
    __tablename__ = "item_types"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name_uk: Mapped[str] = mapped_column(String(255))
    # Wave 2: USD unit cost feeds cost-per-effect metric.
    # NULL means cost unknown; the metric skips those records.
    unit_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)


class Operator(Base):
    __tablename__ = "operators"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name_uk: Mapped[str] = mapped_column(String(255))


class LossReason(Base):
    __tablename__ = "loss_reasons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    name_uk: Mapped[str] = mapped_column(String(255))
    zone: Mapped[Zone] = mapped_column(Enum(Zone, native_enum=False, length=16))


class RepairReason(Base):
    __tablename__ = "repair_reasons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    name_uk: Mapped[str] = mapped_column(String(255))
    zone: Mapped[Zone] = mapped_column(Enum(Zone, native_enum=False, length=16))
