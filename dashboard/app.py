"""Streamlit dashboard with interactive filters and CSV export.

Run from the project root:
    streamlit run dashboard/app.py
"""
import sys
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

# Make src/ importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import analytics  # noqa: E402

st.set_page_config(page_title="E-Commerce Analytics Dashboard", layout="wide")


# ---------------------------------------------------------------- helpers

def rupees(value):
    """Format a number in Indian digit grouping, e.g. 245000 -> ₹2,45,000."""
    n = int(round(float(value or 0)))
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if n < 0 else "") + "₹" + s


def to_date(value):
    ts = pd.to_datetime(value, errors="coerce")
    return date.today() if pd.isna(ts) else ts.date()


def bar_chart(labels, values, title, horizontal=False, xlabel="", ylabel=""):
    fig, ax = plt.subplots(figsize=(8, 4))
    if horizontal:
        ax.barh(labels, values, color="#4f46e5")
        ax.invert_yaxis()
    else:
        ax.bar(labels, values, color="#4f46e5")
        plt.xticks(rotation=45, ha="right")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    fig.tight_layout()
    return fig


def line_chart(x, y, title, xlabel="", ylabel=""):
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(x, y, marker="o", color="#4f46e5")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    plt.xticks(rotation=45, ha="right")
    fig.tight_layout()
    return fig


def show(fig):
    st.pyplot(fig)
    plt.close(fig)


def has_data(df):
    if df.empty:
        st.info("No data for the selected filters.")
        return False
    return True


def download_csv(df, name, tag):
    """CSV download button. Exports raw numbers (not rupee-formatted text)."""
    export = df.copy()
    for col in export.columns:
        if pd.api.types.is_datetime64_any_dtype(export[col]):
            export[col] = export[col].dt.strftime("%Y-%m")
    st.download_button(
        label="Download CSV",
        data=export.to_csv(index=False).encode("utf-8-sig"),  # BOM so Excel reads it correctly
        file_name=f"{name}_{tag}.csv",
        mime="text/csv",
        key=f"dl_{name}",
    )


# ---------------------------------------------------------------- data access

@st.cache_data(ttl=300)
def load_options():
    return analytics.get_filter_options()


@st.cache_data(ttl=300)
def query(name, filters, **kwargs):
    return getattr(analytics, name)(filters, **kwargs)


# ---------------------------------------------------------------- pages

def overview(f, tag):
    revenue = query("total_revenue", f)["total_revenue"].iloc[0]
    counts = query("overview_counts", f).iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Revenue", rupees(revenue))
    c2.metric("Orders", int(counts["total_orders"]))
    c3.metric("Customers (with orders)", int(counts["total_customers"]))
    c4.metric("Products sold", int(counts["total_products"]))

    summary = pd.DataFrame(
        {
            "metric": ["revenue", "orders", "customers_with_orders", "products_sold"],
            "value": [
                float(revenue),
                int(counts["total_orders"]),
                int(counts["total_customers"]),
                int(counts["total_products"]),
            ],
        }
    )
    download_csv(summary, "overview_summary", tag)

    st.subheader("Order status (all statuses, other filters applied)")
    status = query("order_status_counts", f)
    if has_data(status):
        left, right = st.columns([1, 2])
        left.dataframe(status, hide_index=True, width="stretch")
        with left:
            download_csv(status, "order_status", tag)
        with right:
            show(bar_chart(status["order_status"], status["orders"], "Orders by status"))


def sales(f, tag):
    st.subheader("Monthly revenue")
    monthly = query("monthly_revenue", f)
    if has_data(monthly):
        labels = monthly["month"].dt.strftime("%b %Y")
        show(line_chart(labels, monthly["revenue"], "Monthly revenue", ylabel="Revenue (₹)"))
        download_csv(monthly, "monthly_revenue", tag)

    st.subheader("Monthly orders")
    mo = query("monthly_orders", f)
    if has_data(mo):
        show(bar_chart(mo["month"].dt.strftime("%b %Y"), mo["orders"], "Orders per month", ylabel="Orders"))
        download_csv(mo, "monthly_orders", tag)

    st.subheader("Daily revenue")
    daily = query("daily_revenue", f)
    if has_data(daily):
        show(line_chart(daily["day"].astype(str), daily["revenue"], "Daily revenue", ylabel="Revenue (₹)"))
        download_csv(daily, "daily_revenue", tag)


def products(f, tag):
    st.subheader("Top 5 best-selling products")
    df = query("top_products", f, limit=5)
    if has_data(df):
        show(bar_chart(df["product_name"], df["total_sold"], "Units sold", horizontal=True, xlabel="Units"))
        st.dataframe(df, hide_index=True, width="stretch")
        download_csv(df, "top_products", tag)


def customers(f, tag):
    st.subheader("Highest spending customers")
    df = query("top_customers", f, limit=5)
    if has_data(df):
        show(bar_chart(df["customer_name"], df["total_spent"], "Total spent", horizontal=True, xlabel="₹"))
        table = df.copy()
        table["total_spent"] = table["total_spent"].apply(rupees)
        st.dataframe(table, hide_index=True, width="stretch")
        download_csv(df, "top_customers", tag)


def categories(f, tag):
    st.subheader("Category-wise revenue")
    df = query("category_revenue", f)
    if has_data(df):
        show(bar_chart(df["category_name"], df["revenue"], "Revenue by category", ylabel="₹"))
        table = df.copy()
        table["revenue"] = table["revenue"].apply(rupees)
        st.dataframe(table, hide_index=True, width="stretch")
        download_csv(df, "category_revenue", tag)


PAGES = {
    "Overview": overview,
    "Sales Analytics": sales,
    "Product Analytics": products,
    "Customer Analytics": customers,
    "Category Analytics": categories,
}


# ---------------------------------------------------------------- layout

def default_filter_state(opts):
    return {
        "f_dates": (to_date(opts["min_date"]), to_date(opts["max_date"])),
        "f_status": ["Delivered"] if "Delivered" in opts["statuses"] else list(opts["statuses"]),
        "f_cat": list(opts["categories"]),
        "f_city": list(opts["cities"]),
    }


def reset_filters(opts):
    for key, value in default_filter_state(opts).items():
        st.session_state[key] = value


st.title("E-Commerce Analytics Dashboard")

try:
    opts = load_options()

    choice = st.sidebar.radio("Module", list(PAGES.keys()))
    st.sidebar.divider()
    st.sidebar.header("Filters")

    for key, value in default_filter_state(opts).items():
        st.session_state.setdefault(key, value)

    st.sidebar.date_input(
        "Date range",
        min_value=to_date(opts["min_date"]),
        max_value=to_date(opts["max_date"]),
        key="f_dates",
    )
    st.sidebar.multiselect("Order status", opts["statuses"], key="f_status")
    st.sidebar.multiselect("Category", opts["categories"], key="f_cat")
    st.sidebar.multiselect("City", opts["cities"], key="f_city")
    st.sidebar.button("Reset filters", on_click=reset_filters, args=(opts,))
    st.sidebar.button("Refresh data", on_click=st.cache_data.clear)

    dates = st.session_state["f_dates"]
    if not (isinstance(dates, (tuple, list)) and len(dates) == 2):
        st.info("Pick both a start date and an end date in the sidebar.")
        st.stop()
    start, end = dates

    statuses = st.session_state["f_status"]
    cats = st.session_state["f_cat"]
    cities = st.session_state["f_city"]
    if not statuses:
        st.warning("Select at least one order status.")
        st.stop()
    if not cats:
        st.warning("Select at least one category.")
        st.stop()
    if not cities:
        st.warning("Select at least one city.")
        st.stop()

    filters = {
        "start_date": start,
        "end_date": end,
        "statuses": list(statuses),
        # None means "no filter" (everything selected), which keeps the SQL simple
        "categories": None if set(cats) == set(opts["categories"]) else list(cats),
        "cities": None if set(cities) == set(opts["cities"]) else list(cities),
    }
    tag = f"{start}_to_{end}"

    st.caption(
        f"Showing {start} to {end}  |  Status: {', '.join(statuses)}  |  "
        f"Categories: {len(cats)}/{len(opts['categories'])}  |  "
        f"Cities: {len(cities)}/{len(opts['cities'])}"
    )

    PAGES[choice](filters, tag)

except Exception as exc:  # most often: database not running / wrong credentials / data not imported
    st.error(f"Could not load data from PostgreSQL: {exc}")
    st.info(
        "Check that PostgreSQL is running, your DB_* environment variables or .env are correct, "
        "and that you ran: python src/data_import.py --init"
    )
