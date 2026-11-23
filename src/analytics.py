"""SQL analytics: each function runs one query and returns a Pandas DataFrame.

Every query accepts an optional `filters` dict:
    start_date, end_date : datetime.date (inclusive)
    statuses             : list of order statuses
    categories           : list of category names
    cities               : list of customer cities
A missing key means "no filter". An EMPTY list means "match nothing".
With filters=None the spec default applies: Delivered orders only.

Filter values are always sent as bound parameters, never pasted into the SQL
text, so they cannot inject SQL.
"""
import pandas as pd
from sqlalchemy import bindparam, text

from database import engine

DEFAULT_FILTERS = {"statuses": ["Delivered"]}

# All joins start from orders so orders without items are not lost.
BASE_FROM = """
FROM orders o
LEFT JOIN customers c   ON o.customer_id = c.customer_id
LEFT JOIN order_items oi ON o.order_id = oi.order_id
LEFT JOIN products p    ON oi.product_id = p.product_id
LEFT JOIN categories cat ON p.category_id = cat.category_id
"""

REVENUE = "SUM(oi.quantity * oi.unit_price)"


def _resolve(filters):
    return DEFAULT_FILTERS if filters is None else filters


def build_where(filters, ignore_status=False, extra=()):
    """Return (where_sql, params, list_param_names) for a filters dict."""
    f = _resolve(filters)
    clauses = list(extra)
    params = {}
    list_params = []

    if f.get("start_date"):
        clauses.append("o.order_date >= :start_date")
        params["start_date"] = f["start_date"]
    if f.get("end_date"):
        clauses.append("o.order_date <= :end_date")
        params["end_date"] = f["end_date"]

    for key, column in (
        ("statuses", "o.order_status"),
        ("categories", "cat.category_name"),
        ("cities", "c.city"),
    ):
        if key == "statuses" and ignore_status:
            continue
        values = f.get(key)
        if values is None:
            continue
        values = list(values)
        if not values:
            clauses.append("1 = 0")
            continue
        clauses.append(f"{column} IN :{key}")
        params[key] = values
        list_params.append(key)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params, list_params


def _run(query, params=None, list_params=()):
    stmt = text(query)
    if list_params:
        stmt = stmt.bindparams(*[bindparam(name, expanding=True) for name in list_params])
    return pd.read_sql(stmt, engine, params=params or {})


def _month_to_datetime(df):
    """Turn the SQL `month` date column into plain (timezone-free) datetimes.

    orders.order_date is a DATE, so the SQL casts DATE_TRUNC(...) back to a
    date. Without that cast PostgreSQL returns a timestamptz at session-time
    midnight, which pandas shows in UTC (2025-01-01 00:00+05:30 becomes
    2024-12-31 18:30+00:00) and the dashboard labels the wrong month.
    """
    df["month"] = pd.to_datetime(df["month"])
    return df


def get_filter_options():
    """Values that populate the dashboard's filter widgets."""
    statuses = _run("SELECT DISTINCT order_status FROM orders ORDER BY 1")["order_status"].tolist()
    categories = _run(
        "SELECT category_name FROM categories ORDER BY 1"
    )["category_name"].tolist()
    cities = _run(
        "SELECT DISTINCT city FROM customers WHERE city IS NOT NULL ORDER BY 1"
    )["city"].tolist()
    dates = _run("SELECT MIN(order_date) AS min_d, MAX(order_date) AS max_d FROM orders").iloc[0]
    return {
        "statuses": statuses,
        "categories": categories,
        "cities": cities,
        "min_date": dates["min_d"],
        "max_date": dates["max_d"],
    }


# ---- The five core queries from the project spec (now filterable) ----

def total_revenue(filters=None):
    where, params, lp = build_where(filters)
    return _run(
        f"SELECT COALESCE({REVENUE}, 0) AS total_revenue {BASE_FROM} {where}", params, lp
    )


def top_products(filters=None, limit=5):
    where, params, lp = build_where(filters, extra=("p.product_id IS NOT NULL",))
    return _run(
        f"""
        SELECT p.product_name, SUM(oi.quantity) AS total_sold
        {BASE_FROM} {where}
        GROUP BY p.product_name
        ORDER BY total_sold DESC
        LIMIT {int(limit)}
        """,
        params,
        lp,
    )


def monthly_revenue(filters=None):
    where, params, lp = build_where(filters, extra=("oi.order_item_id IS NOT NULL",))
    df = _run(
        f"""
        SELECT DATE_TRUNC('month', o.order_date)::date AS month, {REVENUE} AS revenue
        {BASE_FROM} {where}
        GROUP BY 1
        ORDER BY 1
        """,
        params,
        lp,
    )
    return _month_to_datetime(df)


def top_customers(filters=None, limit=5):
    where, params, lp = build_where(filters, extra=("c.customer_id IS NOT NULL",))
    return _run(
        f"""
        SELECT c.customer_name, {REVENUE} AS total_spent
        {BASE_FROM} {where}
        GROUP BY c.customer_id, c.customer_name
        ORDER BY total_spent DESC
        LIMIT {int(limit)}
        """,
        params,
        lp,
    )


def category_revenue(filters=None):
    where, params, lp = build_where(filters, extra=("cat.category_id IS NOT NULL",))
    return _run(
        f"""
        SELECT cat.category_name, {REVENUE} AS revenue
        {BASE_FROM} {where}
        GROUP BY cat.category_name
        ORDER BY revenue DESC
        """,
        params,
        lp,
    )


# ---- Extra queries used by the dashboard ----

def overview_counts(filters=None):
    where, params, lp = build_where(filters)
    return _run(
        f"""
        SELECT COUNT(DISTINCT o.order_id)    AS total_orders,
               COUNT(DISTINCT o.customer_id) AS total_customers,
               COUNT(DISTINCT oi.product_id) AS total_products
        {BASE_FROM} {where}
        """,
        params,
        lp,
    )


def order_status_counts(filters=None):
    """Ignores the status filter so the full status mix is always visible."""
    where, params, lp = build_where(filters, ignore_status=True)
    return _run(
        f"""
        SELECT o.order_status, COUNT(DISTINCT o.order_id) AS orders
        {BASE_FROM} {where}
        GROUP BY o.order_status
        ORDER BY orders DESC
        """,
        params,
        lp,
    )


def daily_revenue(filters=None):
    where, params, lp = build_where(filters, extra=("oi.order_item_id IS NOT NULL",))
    return _run(
        f"""
        SELECT o.order_date AS day, {REVENUE} AS revenue
        {BASE_FROM} {where}
        GROUP BY o.order_date
        ORDER BY day
        """,
        params,
        lp,
    )


def monthly_orders(filters=None):
    where, params, lp = build_where(filters)
    df = _run(
        f"""
        SELECT DATE_TRUNC('month', o.order_date)::date AS month,
               COUNT(DISTINCT o.order_id) AS orders
        {BASE_FROM} {where}
        GROUP BY 1
        ORDER BY 1
        """,
        params,
        lp,
    )
    return _month_to_datetime(df)


if __name__ == "__main__":
    print("--- Default filters (Delivered only) ---")
    for fn in (
        total_revenue,
        top_products,
        monthly_revenue,
        top_customers,
        category_revenue,
        order_status_counts,
    ):
        print(f"\n=== {fn.__name__} ===")
        print(fn())

    print("\n--- Sample filtered run: Delivered + Pending, Kolkata, Electronics ---")
    sample = {
        "statuses": ["Delivered", "Pending"],
        "cities": ["Kolkata"],
        "categories": ["Electronics"],
    }
    print(total_revenue(sample))

    print("\n--- Safety check: hostile status value must give revenue 0 and break nothing ---")
    hostile = {"statuses": ["x'; DROP TABLE orders;--"]}
    print(total_revenue(hostile))
    print("orders table still exists:", int(overview_counts({"statuses": None}).iloc[0]["total_orders"]), "orders")
