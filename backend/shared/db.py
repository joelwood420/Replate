import contextlib
import datetime

import pyodbc

from shared import config


def to_utc_iso(value: datetime.datetime | None) -> str | None:
    """ISO-format a naive UTC datetime from SQL Server with an explicit offset.

    SQL Server DATETIME2 columns carry no timezone, and `datetime.isoformat()`
    on a naive value omits one too - `new Date(...)` on the JS side then
    parses it as local time instead of UTC, skewing "time ago" displays by
    the client's UTC offset.
    """
    if value is None:
        return None
    return value.replace(tzinfo=datetime.timezone.utc).isoformat()


def _connection_string() -> str:
    return (
        f"Driver={{{config.sql_odbc_driver()}}};"
        f"Server={config.sql_server()};"
        f"Database={config.sql_database()};"
        f"UID={config.sql_uid()};"
        f"PWD={config.sql_pwd()};"
        "TrustServerCertificate=yes;"
    )


@contextlib.contextmanager
def get_connection():
    conn = pyodbc.connect(_connection_string())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
