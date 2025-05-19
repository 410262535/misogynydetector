import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

def connect_to_db():
    try:
        # 使用 Cloud SQL Proxy 的 Unix socket 路徑
        socket_path = f"/cloudsql/{os.getenv('CLOUD_SQL_CONNECTION_NAME')}"

        conn = pymysql.connect(
            unix_socket=socket_path,
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME'),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        print('DB connection successful.')
        return conn
    except Exception as e:
        print(f"DB connection error: {e}")
        return None

def test_db_connection(conn=None):
    if conn:
        print('DB connection successful.')
    else:
        print('DB is not connected.')
        conn = connect_to_db()
        if conn:
            print('Test successful.')
        else:
            print('Failed to connect to the database.')

def close_db_connection(conn=None):
    if conn:
        try:
            conn.close()
            print('DB close successful.')
        except Exception as e:
            print(f'DB close error: {e}')
