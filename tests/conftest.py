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
    url = url or db.url()
    if url in _unreachable:   # found down once: do not wait again for every test
        pytest.skip(_DOWN)
    try:
        return psycopg.connect(url, connect_timeout=3)
    except psycopg.OperationalError:
        if os.environ.get("CI"):
            raise
        _unreachable.add(url)
        pytest.skip(_DOWN)


_unreachable: set[str] = set()
_DOWN = ("Postgres not reachable; start it (`docker compose up -d`, or "
         "`python scripts/dev_pg.py env`) and set DATABASE_URL")


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
