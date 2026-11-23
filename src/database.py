"""Database connection helper.

Credentials are read from environment variables (or a local .env file),
so no password is ever stored in the code or pushed to GitHub.

Variables (defaults in brackets):
    DB_USER [postgres], DB_PASSWORD [""], DB_HOST [localhost],
    DB_PORT [5432], DB_NAME [ecommerce_analytics]
"""
import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional
    pass


def get_engine():
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "ecommerce_analytics"),
    )
    return create_engine(url)


engine = get_engine()


if __name__ == "__main__":
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("Database connection successful!")
