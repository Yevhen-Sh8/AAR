from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from aar_api.core.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = create_async_engine(get_settings().database_url, future=True, echo=False)
_Session = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with _Session() as session:
        yield session
