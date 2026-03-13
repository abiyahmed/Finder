#!/usr/bin/env python3
"""
Truncate all data from the application database (PostgreSQL or SQLite).
Use before hosting to start with a clean DB. Requires --yes to run.
"""
import argparse
import sys
from pathlib import Path

# App root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load env before importing database (database uses dotenv)
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from sqlalchemy import text
from src.infrastructure.database import Base, engine, DATABASE_URL


def truncate_postgres(conn):
    """TRUNCATE all app tables in PostgreSQL. CASCADE handles FKs."""
    tables = [t.name for t in Base.metadata.sorted_tables]
    if not tables:
        print("No tables in metadata.")
        return
    # RESTART IDENTITY resets sequences; CASCADE truncates dependent tables
    sql = f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"
    conn.execute(text(sql))
    conn.commit()
    print(f"Truncated {len(tables)} table(s): {', '.join(tables)}")


def truncate_sqlite(conn):
    """Delete all rows from every table. Disable FKs then re-enable."""
    conn.execute(text("PRAGMA foreign_keys = OFF"))
    conn.commit()
    try:
        for table in Base.metadata.sorted_tables:
            name = table.name
            conn.execute(text(f"DELETE FROM {name}"))
            conn.commit()
            print(f"  Cleared: {name}")
        print(f"Cleared {len(list(Base.metadata.sorted_tables))} table(s).")
    finally:
        conn.execute(text("PRAGMA foreign_keys = ON"))
        conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Truncate all app database data.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm truncation (required to run).",
    )
    args = parser.parse_args()

    if not args.yes:
        print("This will DELETE ALL DATA from the database.")
        print("Run with --yes to confirm.")
        sys.exit(1)

    if ":memory:" in DATABASE_URL:
        print("Refusing to truncate in-memory database (TEST_MODE?). Unset TEST_MODE and use a real DB.")
        sys.exit(1)

    is_pg = "postgresql" in DATABASE_URL
    print(f"Database: {'PostgreSQL' if is_pg else 'SQLite'}")
    print("Truncating...")

    with engine.connect() as conn:
        if is_pg:
            truncate_postgres(conn)
        else:
            truncate_sqlite(conn)

    print("Done. Database is empty.")


if __name__ == "__main__":
    main()
