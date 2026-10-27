
import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv(override=False)


def get_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "hotel_booking")
    )


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
