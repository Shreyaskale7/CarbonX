import os

import psycopg
import pytest
from hypothesis import settings

from carbonx import db

# HYPOTHESIS_PROFILE=thorough: the 10,000-sequence run for invariant 1
# (docs/BUILD_PLAN.md Phase 5). Tests that set max_examples themselves keep it.
settings.register_profile("thorough", max_examples=10_000)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))


def connect(url: str | None = None) -> psycopg.Connection:
    """A connection (default: the app role), or skip locally when Postgres is
    down. In CI, fail instead."""
    try:
        return psycopg.connect(url or db.url(), connect_timeout=3)
    except psycopg.OperationalError:
        if os.environ.get("CI"):
            raise
        pytest.skip("Postgres not reachable; run `docker compose up -d`")


def _rolled_back(url: str | None):
    c = connect(url)
    try:
        yield c
    finally:
        c.rollback()
        c.close()


@pytest.fixture
def conn():
    """The application role (carbonx_app), rolled back afterwards."""
    yield from _rolled_back(None)


@pytest.fixture
def owner_conn():
    """The schema owner, for tests proving a trigger holds even against it.
    Rolled back afterwards."""
    yield from _rolled_back(db.owner_url())


@pytest.fixture
def cur(owner_conn):
    with owner_conn.cursor() as c:
        yield c
