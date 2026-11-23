"""Load the CSV files into PostgreSQL.

Usage (from the project root):
    python src/data_import.py --init     # create tables from database/schema.sql, then load
    python src/data_import.py            # clear tables and reload (tables must exist)
"""
import argparse
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from data_cleaning import clean_all
from database import engine

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SCHEMA_FILE = ROOT / "database" / "schema.sql"

# Parents first, so foreign keys are always satisfied
LOAD_ORDER = ["customers", "categories", "products", "orders", "order_items"]
ID_COLUMNS = {
    "customers": "customer_id",
    "categories": "category_id",
    "products": "product_id",
    "orders": "order_id",
    "order_items": "order_item_id",
}


def read_csvs():
    return {name: pd.read_csv(DATA_DIR / f"{name}.csv") for name in LOAD_ORDER}


def run_schema(conn):
    print("Creating tables from database/schema.sql ...")
    conn.exec_driver_sql(SCHEMA_FILE.read_text(encoding="utf-8"))


def import_data(init=False):
    print("Reading CSV files ...")
    raw = read_csvs()
    print("Cleaning data ...")
    clean = clean_all(raw)

    # One transaction: either everything loads or nothing does
    with engine.begin() as conn:
        if init:
            run_schema(conn)
        else:
            conn.execute(
                text(
                    "TRUNCATE order_items, orders, products, categories, customers "
                    "RESTART IDENTITY CASCADE"
                )
            )

        for name in LOAD_ORDER:
            clean[name].to_sql(name, conn, if_exists="append", index=False)
            print(f"  loaded {len(clean[name])} row(s) into {name}")

        # Keep SERIAL counters ahead of the ids we inserted explicitly
        for name, id_col in ID_COLUMNS.items():
            conn.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{name}', '{id_col}'), "
                    f"COALESCE(MAX({id_col}), 1)) FROM {name}"
                )
            )

    print("Import complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import CSV data into PostgreSQL")
    parser.add_argument("--init", action="store_true", help="(re)create tables first")
    args = parser.parse_args()
    import_data(init=args.init)
