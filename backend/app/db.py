"""Настройка SQLAlchemy + SQLite."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "orders.db")
DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.abspath(_DEFAULT_DB))

_db_dir = os.path.dirname(DATABASE_PATH)
if _db_dir:
    os.makedirs(_db_dir, exist_ok=True)

engine = create_engine(
    f"sqlite:///{DATABASE_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from . import models  # noqa: F401 — регистрация моделей

    Base.metadata.create_all(engine)
