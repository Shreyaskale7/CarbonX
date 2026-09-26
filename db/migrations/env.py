import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

fileConfig(context.config.config_file_name)

# Migrations run as the schema owner; the application never does (0005).
URL = os.environ.get(
    "MIGRATION_DATABASE_URL", "postgresql+psycopg://carbonx:carbonx@localhost:5432/carbonx"
)

# Raw SQL migrations only; no ORM metadata to autogenerate from yet.
with create_engine(URL).connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
