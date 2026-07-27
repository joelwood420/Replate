"""Apply db/schema.sql to a SQL Server / Azure SQL database.

This is the manual counterpart to infra/modules/sql-schema.bicep, which runs the same
file during `az deployment group create`. Use it when:

  * setting up the local dev database (Docker SQL Server 2025 or a native install), or
  * the in-deployment script fails and you need to apply the schema by hand, or
  * you want to re-check the schema without running a full deployment.

schema.sql is idempotent - every CREATE TABLE is guarded by an IF OBJECT_ID(...) IS NULL
check - so running this repeatedly is safe.

Usage:
    # Against whatever backend/.env points at (local dev by default)
    python scripts/apply_schema.py

    # Against a specific server, overriding the environment
    python scripts/apply_schema.py --server myserver.database.windows.net \\
        --database FoodApp --uid replateadmin

    # Show what would run without touching the database
    python scripts/apply_schema.py --dry-run

The password is read from SQL_PWD, or prompted for if --uid is passed without it.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path

# Allow `python scripts/apply_schema.py` from the backend/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"

EXPECTED_TABLES = [
    "Users",
    "Restaurants",
    "MenuItems",
    "Jobs",
    "JobRestaurantCandidates",
    "JobResults",
    "DishElements",
    "ElementIngredients",
    "ElementSteps",
    "CulinaryEmbeddings",
]

# `GO` is a sqlcmd batch separator, not a T-SQL statement - pyodbc cannot execute it, so
# the file is split on it here. Matches GO alone on a line, case-insensitively.
_GO_SEPARATOR = re.compile(r"^\s*GO\s*$", re.IGNORECASE | re.MULTILINE)


def split_batches(sql_text: str) -> list[str]:
    """Split a sqlcmd-style script into batches on GO separators."""
    return [batch.strip() for batch in _GO_SEPARATOR.split(sql_text) if batch.strip()]


def build_connection_string(args: argparse.Namespace) -> str:
    driver = args.driver or os.environ.get("SQL_ODBC_DRIVER", "ODBC Driver 18 for SQL Server")
    server = args.server or os.environ.get("SQL_SERVER")
    database = args.database or os.environ.get("SQL_DATABASE")
    uid = args.uid or os.environ.get("SQL_UID")
    pwd = os.environ.get("SQL_PWD")

    missing = [
        name
        for name, value in (("server", server), ("database", database), ("uid", uid))
        if not value
    ]
    if missing:
        raise SystemExit(
            f"Missing required connection detail(s): {', '.join(missing)}. "
            "Pass them as flags or set SQL_SERVER / SQL_DATABASE / SQL_UID."
        )

    if not pwd:
        pwd = getpass.getpass(f"Password for {uid}@{server}: ")

    return (
        f"Driver={{{driver}}};"
        f"Server={server};"
        f"Database={database};"
        f"UID={uid};"
        f"PWD={pwd};"
        "TrustServerCertificate=yes;"
    )


def verify_tables(cursor) -> list[str]:
    """Return the expected tables that are missing from the database."""
    missing = []
    for table in EXPECTED_TABLES:
        cursor.execute("SELECT OBJECT_ID(?, N'U')", f"dbo.{table}")
        if cursor.fetchone()[0] is None:
            missing.append(table)
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server", help="SQL server hostname. Defaults to $SQL_SERVER.")
    parser.add_argument("--database", help="Database name. Defaults to $SQL_DATABASE.")
    parser.add_argument("--uid", help="SQL login. Defaults to $SQL_UID.")
    parser.add_argument("--driver", help="ODBC driver name. Defaults to $SQL_ODBC_DRIVER.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the batches that would run, without connecting.",
    )
    args = parser.parse_args()

    if not SCHEMA_PATH.exists():
        raise SystemExit(f"Schema file not found: {SCHEMA_PATH}")

    sql_text = SCHEMA_PATH.read_text(encoding="utf-8")
    batches = split_batches(sql_text)
    print(f"Loaded {SCHEMA_PATH} ({len(sql_text)} bytes, {len(batches)} batches).")

    if args.dry_run:
        for index, batch in enumerate(batches, start=1):
            first_line = batch.splitlines()[0]
            print(f"  [{index}] {first_line}")
        print("Dry run - nothing was executed.")
        return 0

    # Imported here so --dry-run and --help work without pyodbc or an ODBC driver present.
    import pyodbc

    # load_dotenv() so the script honours backend/.env the same way shared/config.py does.
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    connection_string = build_connection_string(args)

    with pyodbc.connect(connection_string, autocommit=True) as conn:
        cursor = conn.cursor()
        for index, batch in enumerate(batches, start=1):
            first_line = batch.splitlines()[0]
            print(f"  [{index}/{len(batches)}] {first_line}")
            cursor.execute(batch)

        missing = verify_tables(cursor)

    if missing:
        print(f"\nFAILED - tables missing after apply: {', '.join(missing)}", file=sys.stderr)
        return 1

    print(f"\nSchema applied. All {len(EXPECTED_TABLES)} tables present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
