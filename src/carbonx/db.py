"""Database URLs. The application never connects as the schema owner.

DATABASE_URL            runtime: API, engine, scripts, tests. Role carbonx_app
                        (migration 0005): no DDL, no DELETE/TRUNCATE, cannot
                        disable triggers, so the DB-layer invariants hold
                        against the application.
MIGRATION_DATABASE_URL  Alembic only: the owner role, which can change schema.
"""

import os

APP_DEFAULT = "postgresql://carbonx_app:carbonx_app@localhost:5432/carbonx"
OWNER_DEFAULT = "postgresql://carbonx:carbonx@localhost:5432/carbonx"


def _plain(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def url() -> str:
    return _plain(os.environ.get("DATABASE_URL", APP_DEFAULT))


def owner_url() -> str:
    return _plain(os.environ.get("MIGRATION_DATABASE_URL", OWNER_DEFAULT))
