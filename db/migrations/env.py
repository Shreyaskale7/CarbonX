import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

fileConfig(context.config.config_file_name)

URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://carbonx:carbonx@localhost:5432/carbonx"
)

# Raw SQL migrations only; no ORM metadata to autogenerate from yet.
with create_engine(URL).connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
