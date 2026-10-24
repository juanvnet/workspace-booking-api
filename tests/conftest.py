"""Shared test setup: a test database, an API client and a logged-in user"""

import os

# Use an in-memory database and a test key instead of the values in .env
# This must happen before importing the app, because the settings are read on import
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-key-only-used-in-the-tests"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import create_access_token, hash_password
from app.database import get_session
from app.main import app
from app.models import User

TEST_PASSWORD = "test-password"

# StaticPool keeps one single connection, so the in-memory database is shared
# between the tests and the API (which runs in another thread).
engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


@pytest.fixture
def session():
    """An empty database for each test"""
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)


@pytest.fixture
def client(session):
    """Calls the API using the test database instead of the real one"""
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def user(session) -> User:
    user = User(
        email="pepe@example.com",
        full_name="Pepe Prado",
        hashed_password=hash_password(TEST_PASSWORD),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture
def user_headers(user) -> dict:
    """Authorization header with a valid token for `user`"""
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}
