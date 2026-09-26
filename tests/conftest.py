import os

import psycopg
import pytest

URL = os.environ.get(
    "DATABASE_URL", "postgresql://carbonx:carbonx@localhost:5432/carbonx"
).replace("postgresql+psycopg://", "postgresql://")


def connect() -> psycopg.Connection:
    """A connection, or skip locally when Postgres is down. In CI, fail instead."""
    try:
        return psycopg.connect(URL, connect_timeout=3)
    except psycopg.OperationalError:
        if os.environ.get("CI"):
            raise
        pytest.skip("Postgres not reachable; run `docker compose up -d`")


@pytest.fixture
def conn():
    """A connection whose work is rolled back, leaving the DB clean."""
    c = connect()
    try:
        yield c
    finally:
        c.rollback()
        c.close()


@pytest.fixture
def cur(conn):
    with conn.cursor() as c:
        yield c
