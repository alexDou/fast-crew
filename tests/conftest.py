from collections.abc import Callable, Generator
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from faker import Faker
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import Session

from src.app.core.config import settings
from src.app.main import app

sync_engine = create_engine(settings.POSTGRES_SYNC_DATABASE_URL)
local_session = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)


fake = Faker()


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, Any, None]:
    with TestClient(app) as _client:
        yield _client
    app.dependency_overrides = {}
    sync_engine.dispose()


@pytest.fixture
def db() -> Generator[Session, Any, None]:
    session = local_session()
    yield session
    session.close()


def override_dependency(dependency: Callable[..., Any], mocked_response: Any) -> None:
    app.dependency_overrides[dependency] = lambda: mocked_response


@pytest.fixture
def mock_db():
    """Mock database session for unit tests."""
    return Mock(spec=AsyncSession)


@pytest.fixture
def mock_redis():
    """Mock Redis connection for unit tests."""
    mock_redis = Mock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=True)
    return mock_redis


@pytest.fixture
def sample_user_data():
    """Generate sample user data for tests."""
    return {
        "name": fake.name(),
        "username": fake.user_name(),
        "email": fake.email(),
        "password": fake.password(),
    }


_SAFE_NAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -")


def _faker_safe_name() -> str:
    """Strip out characters that would violate the UserRead name regex.

    ``fake.name()`` sometimes produces titles like ``Mr. Brian Anderson`` or
    suffixes like ``Nicholas Arellano III`` that contain punctuation which
    the ``^[a-zA-Z0-9 \\-]+$`` constraint rejects. We preserve determinism by
    keeping faker's output but filter it through the allowed character set.
    """
    candidate = "".join(ch for ch in fake.name() if ch in _SAFE_NAME_CHARS).strip()
    return candidate or "User Userson"


@pytest.fixture
def sample_user_read():
    """Generate a sample UserRead object."""
    from src.app.schemas.user import UserRead

    return UserRead(
        id=1,
        name=_faker_safe_name(),
        username=fake.user_name(),
        email=fake.email(),
    )


@pytest.fixture
def current_user_dict():
    """Mock current user from auth dependency."""
    return {
        "id": 1,
        "username": fake.user_name(),
        "email": fake.email(),
        "name": fake.name(),
        "is_superuser": False,
    }
