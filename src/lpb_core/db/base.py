"""SQLAlchemy engine, sessionmaker, declarative base."""

from collections.abc import Iterator
from datetime import datetime
from uuid import UUID

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from lpb_core.settings import settings

# Predictable constraint names so Alembic generates clean migrations.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    type_annotation_map = {
        UUID: __import__("sqlalchemy.dialects.postgresql", fromlist=["UUID"]).UUID(as_uuid=True),
        datetime: __import__("sqlalchemy").DateTime(timezone=True),
    }


engine = create_engine(
    settings.database_url_sync,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_session() -> Iterator[Session]:
    """FastAPI / worker dependency for a per-request DB session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
