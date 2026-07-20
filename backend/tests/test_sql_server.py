import os

import pyodbc
from dotenv import load_dotenv

load_dotenv()

conn_str = (
    "Driver={ODBC Driver 18 for SQL Server};"
    f"Server={os.environ['SQL_SERVER']};"
    f"Database={os.environ['SQL_DATABASE']};"
    f"UID={os.environ['SQL_UID']};"
    f"PWD={os.environ['SQL_PWD']};"
    "TrustServerCertificate=yes;"
)

conn = pyodbc.connect(conn_str)
cursor = conn.cursor()
cursor.execute("SELECT @@VERSION;")
print(cursor.fetchone()[0])
 

cursor = conn.cursor()
cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES ORDER BY TABLE_NAME;")
for row in cursor.fetchall():
    print(row[0])

conn.close()