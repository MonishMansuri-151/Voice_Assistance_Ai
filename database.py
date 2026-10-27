
import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv(override=False)


def get_connection():
    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "22738")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        ssl_disabled=False
    )

    cursor = conn.cursor()
    cursor.execute("SELECT DATABASE()")
    print("DEBUG DATABASE:", cursor.fetchone()[0])

    cursor.execute("""
        SELECT TABLE_NAME
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
    """)
    print("DEBUG TABLES:", [row[0] for row in cursor.fetchall()])

    cursor.close()
    return conn


def test_connection():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DATABASE()")
        print("MySQL Connected Successfully!")
        print("Database:", cursor.fetchone()[0])
        cursor.close()
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        test_connection()
    except Exception as e:
        print("Database connection failed:", e)
