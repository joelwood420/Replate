import contextlib

import pyodbc

from shared import config


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
