import pyodbc

conn_str = (
    "Driver={ODBC Driver 18 for SQL Server};"
    "Server=localhost;"
    "Database=FoodApp;"
    "UID=app_user;"
    "PWD=<your_password_here>;"
    "TrustServerCertificate=yes;"
)

conn = pyodbc.connect(conn_str)
cursor = conn.cursor()
cursor.execute("SELECT @@VERSION;")
print(cursor.fetchone()[0])
conn.close()