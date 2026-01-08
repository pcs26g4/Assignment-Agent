"""
Test database connection script
Run this to verify your PostgreSQL connection settings
"""
import os
from dotenv import load_dotenv
import psycopg2
from psycopg2 import OperationalError

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:manoj_gunda@localhost:5432/task"
)

def test_connection():
    """Test PostgreSQL connection"""
    print("Testing PostgreSQL connection...")
    print(f"Connection string: {DATABASE_URL.split('@')[0]}@***")
    
    try:
        # Parse connection string
        # Format: postgresql://username:password@host:port/database
        conn_string = DATABASE_URL.replace("postgresql://", "")
        parts = conn_string.split("@")
        user_pass = parts[0].split(":")
        host_db = parts[1].split("/")
        host_port = host_db[0].split(":")
        
        username = user_pass[0]
        password = user_pass[1] if len(user_pass) > 1 else ""
        host = host_port[0]
        port = host_port[1] if len(host_port) > 1 else "5432"
        database = host_db[1] if len(host_db) > 1 else "postgres"
        
        print(f"\nConnection details:")
        print(f"  Host: {host}")
        print(f"  Port: {port}")
        print(f"  Database: {database}")
        print(f"  Username: {username}")
        print(f"  Password: {'*' * len(password)}")
        
        # Try to connect
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=username,
            password=password
        )
        
        print("\n[SUCCESS] Connection successful!")
        conn.close()
        return True
        
    except OperationalError as e:
        print(f"\n[ERROR] Connection failed!")
        print(f"Error: {e}")
        print("\nPossible issues:")
        print("1. PostgreSQL is not running")
        print("2. Wrong username or password")
        print("3. Database does not exist")
        print("4. Connection string format is incorrect")
        return False
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        return False

if __name__ == "__main__":
    test_connection()

