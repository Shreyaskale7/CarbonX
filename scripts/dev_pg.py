"""A local Postgres for development WITHOUT Docker. A stand-in, not the target.

    pip install pixeltable-pgserver        # bundles Postgres binaries; dev only
    python scripts/dev_pg.py reset         # fresh database, all migrations applied
    python scripts/dev_pg.py env           # prints the two variables to export
    python scripts/dev_pg.py stop

The real target is Postgres 16 with btree_gist and pgcrypto (docker-compose.yml,
and CI). The pip-installable Postgres has neither extension, so this tool
applies the SAME migration SQL through two translations:

  pgcrypto    digest(text, 'sha256') is defined from the built-in sha256().
              Identical hashes.
  btree_gist  it only supplies "=" for plain columns inside EXCLUDE
              constraints. `col WITH =` is rewritten to
              `fn_eq(col) WITH &&`, where fn_eq(x) is the one-point range
              [x, x]. Two one-point ranges overlap exactly when the values are
              equal, so the constraint accepts and rejects the same rows and
              raises the same error (exclusion_violation).

So this checks the schema, triggers, grants and application SQL for real. It
does NOT prove the btree_gist form works, and it is a different Postgres
version. A green run here is evidence; CI on Postgres 16 is the authority.
"""
import importlib.util
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "carbonx_pg"
VERSIONS = ROOT / "db" / "migrations" / "versions"

PRELUDE = """
CREATE FUNCTION digest(text, text) RETURNS bytea AS $$
    SELECT CASE WHEN $2 = 'sha256' THEN sha256(convert_to($1, 'UTF8')) END
$$ LANGUAGE sql IMMUTABLE;
CREATE TYPE textrange AS RANGE (subtype = text);
CREATE FUNCTION fn_eq(bigint) RETURNS int8range AS
    $$ SELECT int8range($1, $1, '[]') $$ LANGUAGE sql IMMUTABLE;
-- Schema-qualified: Postgres 17+ evaluates index expressions with a restricted
-- search_path, where an unqualified type in public is not found.
CREATE FUNCTION fn_eq(text) RETURNS public.textrange AS
    $$ SELECT public.textrange($1, $1, '[]') $$ LANGUAGE sql IMMUTABLE;
"""


def translate(sql: str) -> str:
    sql = re.sub(r"CREATE EXTENSION IF NOT EXISTS (?:btree_gist|pgcrypto);", "", sql)

    def exclude(m: re.Match) -> str:
        return "EXCLUDE USING gist (" + re.sub(
            r"(\w+)\s+WITH\s+=", r"fn_eq(\1) WITH &&", m[1]) + ")"

    sql = re.sub(r"EXCLUDE USING gist \((.*?)\)", exclude, sql, flags=re.DOTALL)
    # The one plain GiST index with a text column.
    return sql.replace("USING gist (factor_key, valid_time, system_time_range)",
                       "USING gist (fn_eq(factor_key), valid_time, system_time_range)")


def migrations() -> list[tuple[str, str]]:
    out = []
    for path in sorted(VERSIONS.glob("0*.py")):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sql = module.UPGRADE if hasattr(module, "UPGRADE") else \
            module.SCHEMA.read_text(encoding="utf-8")
        out.append((module.revision, sql))
    return out


def server():
    try:
        import pixeltable_pgserver as pgserver
    except ImportError:
        sys.exit("pip install pixeltable-pgserver  (development only)")
    return pgserver.get_server(str(DATA), cleanup_mode=None)


def urls(srv) -> tuple[str, str]:
    base = srv.get_uri().rsplit("/", 1)[0]          # postgresql://postgres:@host:port
    host = base.split("@", 1)[1]
    return (f"postgresql://carbonx_app:carbonx_app@{host}/carbonx", f"{base}/carbonx")


def reset() -> None:
    import psycopg
    srv = server()
    app_url, owner_url = urls(srv)
    admin = srv.get_uri()
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute("DROP DATABASE IF EXISTS carbonx WITH (FORCE)")
        conn.execute("CREATE DATABASE carbonx")
    with psycopg.connect(owner_url) as conn:
        conn.execute(PRELUDE)
        revision = None
        for revision, sql in migrations():
            conn.execute(translate(sql))
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
        conn.execute("INSERT INTO alembic_version VALUES (%s)", (revision,))
    print(f"dev database ready at revision {revision} (compatibility mode)")
    print_env(app_url, owner_url)


def print_env(app_url: str, owner_url: str) -> None:
    print(f"export DATABASE_URL='{app_url}'")
    print(f"export MIGRATION_DATABASE_URL='{owner_url}'")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "env"
    if command == "reset":
        reset()
    elif command == "env":
        print_env(*urls(server()))
    elif command == "stop":
        server().cleanup()
        print("stopped")
    else:
        sys.exit(__doc__)
