"""Data cleaning and validation with Pandas.

Each clean_* function returns a cleaned DataFrame. clean_all() also removes
rows whose foreign keys point to rows that were dropped earlier.
"""
import pandas as pd

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
VALID_STATUSES = {"Delivered", "Pending", "Cancelled"}


def _report(name, before, after):
    dropped = before - after
    if dropped:
        print(f"  [{name}] dropped {dropped} invalid/duplicate row(s)")


def clean_customers(df):
    before = len(df)
    df = df.copy()
    df["customer_name"] = df["customer_name"].astype(str).str.strip()
    df["email"] = df["email"].astype(str).str.strip().str.lower()
    df["city"] = df["city"].astype(str).str.strip().str.title()
    df["registration_date"] = pd.to_datetime(df["registration_date"], errors="coerce").dt.date
    df = df[df["customer_name"] != ""]
    df = df[df["email"].str.match(EMAIL_PATTERN, na=False)]
    df = df.drop_duplicates(subset="email", keep="first")
    df = df.drop_duplicates(subset="customer_id", keep="first")
    _report("customers", before, len(df))
    return df


def clean_categories(df):
    before = len(df)
    df = df.copy()
    df["category_name"] = df["category_name"].astype(str).str.strip()
    df = df[df["category_name"] != ""]
    df = df.drop_duplicates(subset="category_name", keep="first")
    df = df.drop_duplicates(subset="category_id", keep="first")
    _report("categories", before, len(df))
    return df


def clean_products(df, valid_category_ids):
    before = len(df)
    df = df.copy()
    df["product_name"] = df["product_name"].astype(str).str.strip()
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["stock_quantity"] = pd.to_numeric(df["stock_quantity"], errors="coerce")
    df = df.dropna(subset=["product_name", "price", "stock_quantity"])
    df = df[(df["price"] >= 0) & (df["stock_quantity"] >= 0)]
    df = df[df["category_id"].isin(valid_category_ids)]
    df = df.drop_duplicates(subset="product_id", keep="first")
    df["stock_quantity"] = df["stock_quantity"].astype(int)
    _report("products", before, len(df))
    return df


def clean_orders(df, valid_customer_ids):
    before = len(df)
    df = df.copy()
    df["order_status"] = df["order_status"].astype(str).str.strip().str.title()
    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce").dt.date
    df = df.dropna(subset=["order_date"])
    df = df[df["order_status"].isin(VALID_STATUSES)]
    df = df[df["customer_id"].isin(valid_customer_ids)]
    df = df.drop_duplicates(subset="order_id", keep="first")
    _report("orders", before, len(df))
    return df


def clean_order_items(df, valid_order_ids, valid_product_ids):
    before = len(df)
    df = df.copy()
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    df = df.dropna(subset=["quantity", "unit_price"])
    df = df[(df["quantity"] > 0) & (df["unit_price"] >= 0)]
    df = df[df["order_id"].isin(valid_order_ids) & df["product_id"].isin(valid_product_ids)]
    df = df.drop_duplicates(subset="order_item_id", keep="first")
    df["quantity"] = df["quantity"].astype(int)
    _report("order_items", before, len(df))
    return df


def clean_all(raw):
    """raw: dict of DataFrames keyed by table name. Returns cleaned dict."""
    customers = clean_customers(raw["customers"])
    categories = clean_categories(raw["categories"])
    products = clean_products(raw["products"], set(categories["category_id"]))
    orders = clean_orders(raw["orders"], set(customers["customer_id"]))
    order_items = clean_order_items(
        raw["order_items"], set(orders["order_id"]), set(products["product_id"])
    )
    return {
        "customers": customers,
        "categories": categories,
        "products": products,
        "orders": orders,
        "order_items": order_items,
    }
