import os
import sys
from pathlib import Path

import pytest

# Ensure tests can import the `app` package from the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Force a dedicated SQLite test database for the whole test session.
TEST_DATABASE_FILE = Path(__file__).parent / "test_app.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE_FILE}"

from app import app, db


@pytest.fixture(autouse=True)
def reset_database_schema_before_and_after_each_test():
    """
    Reset DB schema around each test to guarantee isolation.

    Autouse=True means every test gets a clean schema automatically,
    avoiding cross-test data leakage.
    """
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
    )

    with app.app_context():
        db.drop_all()
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()


@pytest.fixture
def http_client():
    """Provide a Flask test client for route/API requests."""
    with app.test_client() as client:
        yield client


@pytest.fixture
def client(http_client):
    """Alias fixture kept for compatibility with existing test names."""
    return http_client
