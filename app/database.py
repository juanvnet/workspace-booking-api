"""Database connection and session dependency"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

engine = create_engine(settings.database_url)


def create_db_and_tables() -> None:
    """Create all tables defined in app/models.py if they do not exist"""
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """Open a database session for one request and close it afterwards"""
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
