"""Database initialization helper.

The script performs the steps that are needed before the backend can talk to a
database:

1. create the business database when it does not exist yet (PostgreSQL only),
2. create the LangGraph checkpoint database - it lives in a database of its own,
3. bring the schema up to the latest revision with Alembic.

It is platform independent on purpose - the ``init_db.sh`` and ``init_db.ps1``
wrappers only forward their arguments to this module.

Usage::

    python scripts/init_db.py                 # create database if needed + upgrade head
    python scripts/init_db.py --create-db     # only create the database
    python scripts/init_db.py --reset         # downgrade base, then upgrade head
    python scripts/init_db.py --revision 0001  # upgrade to a specific revision

The DSN is resolved from the application settings (environment variables), so no
credential is ever passed on the command line or stored in this file.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

#: Directory that contains the ``app`` package and ``alembic.ini``.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402  (needs the sys.path entry above)

#: Database names are used verbatim in a ``CREATE DATABASE`` statement, so only
#: the identifier subset that PostgreSQL accepts unquoted is allowed.
SAFE_DB_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


def run_alembic(*args: str) -> None:
    """Run ``python -m alembic <args>`` inside the backend directory."""

    command = [sys.executable, "-m", "alembic", *args]
    print(f"$ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=BACKEND_DIR, check=True)  # noqa: S603


async def create_database_if_missing(dsn: str) -> bool:
    """Create the target database when it is absent.

    Returns ``True`` when a new database was created. SQLite is ignored: the
    engine creates the file on its own.
    """

    url = make_url(dsn)
    if url.get_backend_name() != "postgresql":
        print(f"[init-db] skip database creation: {url.get_backend_name()} is not PostgreSQL")
        return False

    database = url.database or ""
    if not SAFE_DB_NAME.match(database):
        raise SystemExit(
            f"[init-db] refusing to create a database with an unsafe name: {database!r}"
        )

    maintenance_url = url.set(database="postgres")
    engine = create_async_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": database},
            )
            if exists:
                print(f"[init-db] database {database!r} already exists")
                return False
            # CREATE DATABASE cannot run inside a transaction; AUTOCOMMIT handles that.
            await connection.execute(text(f'CREATE DATABASE "{database}"'))
            print(f"[init-db] database {database!r} created")
            return True
    finally:
        await engine.dispose()


async def create_checkpoint_database_if_missing(dsn: str) -> bool:
    """Create the LangGraph checkpoint database when it is absent.

    The checkpointer keeps its tables in a database of its own, so the tables
    never mix with the business schema. The DSN is written for psycopg
    (``postgresql://``); it is rewritten to the async driver because the
    creation itself runs on the SQLAlchemy async engine.
    """

    url = make_url(dsn)
    if url.get_backend_name() != "postgresql":
        print(f"[init-db] skip checkpoint database creation: {url.get_backend_name()}")
        return False

    database = url.database or ""
    if not SAFE_DB_NAME.match(database):
        raise SystemExit(
            f"[init-db] refusing to create a checkpoint database with an unsafe name: {database!r}"
        )

    maintenance_url = url.set(drivername="postgresql+asyncpg", database="postgres")
    engine = create_async_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": database},
            )
            if exists:
                print(f"[init-db] checkpoint database {database!r} already exists")
                return False
            await connection.execute(text(f'CREATE DATABASE "{database}"'))
            print(f"[init-db] checkpoint database {database!r} created")
            return True
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    """Entry point of the initialization script."""

    parser = argparse.ArgumentParser(description="Initialize the platform database.")
    parser.add_argument(
        "--create-db",
        action="store_true",
        help="only create the database when it does not exist, skip the migration",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="run 'downgrade base' before 'upgrade head' (destructive, drops all tables)",
    )
    parser.add_argument(
        "--revision",
        default="head",
        help="target revision for the upgrade step (default: head)",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    print(f"[init-db] target: {settings.masked_database_uri}")
    print(f"[init-db] checkpoint target: {settings.masked_checkpoint_database_uri}")

    asyncio.run(create_database_if_missing(settings.sqlalchemy_database_uri))
    asyncio.run(create_checkpoint_database_if_missing(settings.checkpoint_database_uri))
    if args.create_db:
        return 0

    if args.reset:
        run_alembic("downgrade", "base")
    run_alembic("upgrade", args.revision)
    print("[init-db] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
