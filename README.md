# E-Commerce Sales Analytics System

A beginner Data Engineering project: store e-commerce sales data in PostgreSQL, analyse it with SQL, and explore the results in a Streamlit dashboard.

**Stack:** Python, PostgreSQL, SQL, Pandas, SQLAlchemy, Streamlit, Matplotlib

## What it answers
- How much revenue is generated?
- Which products sell the most?
- Who are the most valuable customers?
- Which categories earn the most?
- How many orders are placed each month?
- How many orders are pending, delivered or cancelled?

Revenue figures count **Delivered** orders only by default (you can change this with the Order status filter, see below).

## Features

### Interactive filters
The dashboard sidebar has a **Filters** section that applies to every module (Overview, Sales Analytics, Product Analytics, Customer Analytics, Category Analytics):

| Filter | What it does | Default |
|---|---|---|
| **Date range** | Keeps orders placed between the start and end date | Full range in the data |
| **Order status** | Multiselect of order statuses | Delivered |
| **Category** | Multiselect of product categories | All categories |
| **City** | Multiselect of customer cities | All cities |

- **Reset filters** restores the defaults.
- **Refresh data** clears the query cache (results are cached for 5 minutes) so new database changes show up.
- A caption under the title shows which filters are active.
- If a filter has nothing selected, or only one end of the date range is picked, the dashboard shows a short message instead of an error. If the filters match no rows, each section shows "No data for the selected filters."
- The "Order status" table on the Overview page ignores the Order status filter, so you always see the full status mix (the other filters still apply).

### CSV export
Every table and chart has a **Download CSV** button beneath it (8 in total): overview summary, order status, monthly revenue, monthly orders, daily revenue, top products, top customers and category revenue.
- The export reflects the current filters, and the filename includes the date range, for example `monthly_revenue_2025-01-01_to_2025-06-30.csv`.
- Files contain raw numbers (not rupee-formatted text) and months as `YYYY-MM`.
- Files are saved as UTF-8 with a BOM so they open correctly in Excel.
- No download button appears when there is no data to export.

### Safe, parameterized queries
Filter values are never pasted into SQL strings. `src/analytics.py` builds the `WHERE` clause with `build_where()` and passes values as bound parameters (lists use SQLAlchemy's expanding `IN` bindings). This prevents SQL injection. Running `python src/analytics.py` includes a check that a hostile input string returns no rows and leaves the `orders` table intact. Calling a query function without filters uses `DEFAULT_FILTERS` (Delivered orders only), so results match the original unfiltered queries.

## Project structure
```
E-Commerce Sales Analytics System/
├── data/          customers, categories, products, orders, order_items (CSV)
├── database/      schema.sql (5 tables, constraints, indexes)
├── src/
│   ├── database.py       SQLAlchemy engine (credentials from .env)
│   ├── data_cleaning.py  Pandas cleaning and validation
│   ├── data_import.py    Loads cleaned CSVs into PostgreSQL
│   └── analytics.py      Filter-aware SQL queries as Python functions
├── dashboard/
│   ├── app.py                Streamlit dashboard (5 modules, filters, CSV export)
│   ├── mockup.html           Static design mockup
│   └── mockup_filters.html   Static mockup of the filter sidebar and CSV buttons
├── requirements.txt
├── .env.example
└── README.md
```

## Setup

1. **Install PostgreSQL** and open pgAdmin.

2. **Create the database** (in pgAdmin's Query Tool, connected to `postgres`):
   ```sql
   CREATE DATABASE ecommerce_analytics;
   ```

3. **Create a virtual environment and install packages** (from the project folder):
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

4. **Add your database credentials.** Copy `.env.example` to `.env` and put in your PostgreSQL password. Never commit `.env`.

5. **Test the connection:**
   ```
   python src/database.py
   ```
   Expected: `Database connection successful!`

6. **Create tables and load the data:**
   ```
   python src/data_import.py --init
   ```
   Expected: customers 20, categories 5, products 15, orders 40, order_items 70. The cleaning step drops 2 customer rows on purpose (one invalid email, one duplicate email) and fixes the lowercase `delivered` status on order 27.

   To reload later without recreating tables: `python src/data_import.py`

7. **Check the SQL results in the terminal:**
   ```
   python src/analytics.py
   ```

8. **Start the dashboard:**
   ```
   streamlit run dashboard/app.py
   ```
   The dashboard needs Streamlit 1.50 or newer (already set in `requirements.txt`). If you upgraded from an older version, run `pip install -r requirements.txt` again.

## Database design
Five tables: `customers`, `categories`, `products`, `orders`, `order_items`.
- One customer places many orders; one order has many items; one product appears in many items; one category holds many products.
- `unit_price` is stored in `order_items` so the price charged at order time is kept even if the product price changes later.
- Primary keys, foreign keys, `UNIQUE` and `CHECK` constraints protect data integrity. Indexes speed up joins and status filters.

## DBMS concepts demonstrated
Primary keys, foreign keys, constraints, normalization, joins, indexes. The import runs inside a single transaction (all-or-nothing). Views are a good next step, for example saving the Delivered-revenue query as a view.

## Troubleshooting
- **password authentication failed:** check `DB_PASSWORD` in `.env`.
- **relation does not exist:** run `python src/data_import.py --init`.
- **Dashboard shows an error panel:** PostgreSQL may not be running, or data has not been imported.
