"""Test harness: a dedicated database migrated with Alembic; every test runs inside a rolled-back transaction."""

import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import API_DIR, settings
from app.core.ratelimit import limiter
from app.db.session import get_db
from app.main import app

TEST_URL = settings.test_database_url
CSRF = {"X-Requested-With": "plasticloop"}
# Never let device tests rewrite the live broker's password file (the api container mounts the shared volume).
settings.mqtt_passwd_file = Path(tempfile.mkdtemp(prefix="pl-mqtt-")) / "passwd"


def _recreate_database(url: str) -> None:
    target = make_url(url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{target.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def engine():
    _recreate_database(TEST_URL)
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_URL)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    eng = create_engine(TEST_URL)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False, autoflush=False)
    yield session
    session.close()
    outer.rollback()
    connection.close()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    limiter.reset()
    # Not used as a context manager, so the app lifespan (broker credential sync) never touches the dev database.
    yield TestClient(app)
    app.dependency_overrides.clear()


def cookie_client(**cookies) -> TestClient:
    """A client whose cookie jar holds exactly the given cookies (for replaying refresh tokens)."""
    return TestClient(app, cookies=cookies)
