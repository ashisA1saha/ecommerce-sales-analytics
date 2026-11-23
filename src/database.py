
"""Database connection helper for local PostgreSQL and Streamlit Cloud."""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

try:
    from dotenv import load_dotenv
    load_dotenv(".env.neon", override=True)
except ImportError:
    pass


def get_setting(key, default=""):
    """Read Streamlit secrets first, then local environment variables."""
    try:
        import streamlit as st
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass

    return os.getenv(key, default)


def get_engine():
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=get_setting("DB_USER", "postgres"),
        password=get_setting("DB_PASSWORD", ""),
        host=get_setting("DB_HOST", "localhost"),
        port=int(get_setting("DB_PORT", "5432")),
        database=get_setting("DB_NAME", "ecommerce_analytics"),
        query={
            "sslmode": get_setting("DB_SSLMODE", "prefer")
        },
    )

    return create_engine(url, pool_pre_ping=True)


engine = get_engine()


if __name__ == "__main__":
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    print("Database connection successful!")
