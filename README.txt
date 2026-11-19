# Order Inventory Service

A Django REST Framework API for product inventory, order placement, and PostgreSQL-backed product search.
The application provides stock-safe order processing using PostgreSQL transactions and row-level locking to prevent overselling under concurrent requests. 

# Installation and Setup

> Prerequisites
Install the following:

Python 3.10 or compatible project-supported version.
PostgreSQL.
Git.
Docker Desktop

From the repository root, create and activate a virtual environment, then install dependencies:

> Activate virtual environment

python -m venv .venv
.\.venv\Scripts\Activate.ps1

> Configure PostgreSQL

Create a PostgreSQL database and database role.

In psql prompt,
sudo -u postgres psql

CREATE DATABASE mydb;
CREATE USER myuser WITH ENCRYPTED PASSWORD 'mypassword';
ALTER ROLE myuser SET client_encoding TO 'utf8';
ALTER ROLE myuser SET default_transaction_isolation TO 'read committed';
ALTER ROLE myuser SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE mydb TO myuser;


What the project contains :-

- core/ configures Django, database settings, and root URL routing.
- apps/products/ contains product data, product CRUD endpoints, and PostgreSQL full-text search.
- apps/orders/ contains orders, order items, validation, and the stock-safe order placement service.
- apps/reports/ contains an aggregate sales report endpoint.
- load_test.py sends concurrent order and report requests and checks the final stock count.

> Configure environment variables

Add a .env file in the repository root. The application loads this file through python-dotenv:

.env contains credentials :-

SECRET_KEY=local-secret
DB_NAME=order_inventory
DB_USER=order_inventory_user
DB_PASSWORD=database-password
DB_HOST=localhost
DB_PORT=5432

Apply migrations and start Django's development server:

python manage.py makemigrations
python manage.py migrate
python manage.py runserver

The server is available at 'http://127.0.0.1:8000/'. 
The Django admin is at /admin/; create an admin account with python manage.py createsuperuser  
Product records can be managed through the product API or admin.

# API Documentation


All API routes use the /api/v1/ prefix.


GET  /api/v1/products/ ->  List active products 
POST  /api/v1/products/ -> Create a product 
GET, PUT, PATCH, DELETE  /api/v1/products/{id}/  Retrieve or manage a product 
GET /api/v1/products/search/?q=laptop -> Search active products by name and description, ordered by relevance 
POST /api/v1/orders/ -> Place an order and decrement inventory atomically 
GET -> /api/v1/orders/{id}/ -> Retrieve an order with its items 
GET /api/v1/reports/sales/ -> Aggregate confirmed order count, revenue, and per-product sales

Example:
{
  "items": [
    {"product_id": 1, "quantity": 2},
    {"product_id": 3, "quantity": 1}
  ]
}

Create a product in Postman with `POST /api/v1/products/`:
{
  "name": "Orion Laptop",
  "description": "Portable computer for QA testing",
  "price": "1250.00",
  "stock": 25,
  "is_active": true
}


Save the returned product ID. Search by its name or description. 
Product list and search endpoints include active products only. The list is ordered newest first.

Place an order using POST /api/v1/orders/:

{
  "items": [
    {"product_id": 1, "quantity": 2},
    {"product_id": 2, "quantity": 1}
  ]
}


Each quantity must be a positive integer and items must be non-empty. 
Duplicate product IDs are combined. A successful order returns 201; invalid products or insufficient stock return 400. 
Retrieve the result with GET /api/v1/orders/{returned_order_id}/.

Design decisions and trade-offs

Order consistency under concurrency

apps/orders/api/v1/services.py wraps order creation in transaction.atomic. 
It combines repeated product IDs, locks the affected product rows with select_for_update() in ascending ID order, validates active status and stock,
then updates stock and creates the order and items in that transaction.

The row locks prevent two concurrent orders from both reading and consuming the same remaining stock. 
Locking in a consistent order reduces deadlock risk for orders containing overlapping products. 
The transaction ensures a failure rolls back the inventory and order changes together. 
The trade-off is that competing requests for a popular product wait for its row lock.


Connection handling and concurrency

Database access uses Django's PostgreSQL backend and psycopg 3. Connection parameters come from environment variables loaded from .env for local development. 
Django manages connections through its request lifecycle; 
this project does not configure persistent connections (`CONN_MAX_AGE`) or a separate pooler. This keeps the deployment model simple and avoids keeping idle connections open by default, at the cost of connection setup overhead under sustained traffic. For production, size the application worker count against PostgreSQL's connection limit and consider a managed pooler or explicitly configured persistent connections when measured workload justifies it.


Search design and trade-offs

Product search uses PostgreSQL full-text search rather than substring matching or an external search service. 
Product.search_vector stores preprocessed tokens, and a GIN index supports matching at scale. 
A database trigger maintains the vector when product name or description changes, including updates made outside Django; 
a migration backfills existing rows. The search API parses input with PostgreSQL's english websearch query syntax and ranks matching active products with SearchRank.

This keeps search and product data in the same database, avoids operating another service, and provides stemming, 
query syntax, indexed matching, and relevance ordering. 
The English text configuration is language-specific, and full-text search matches tokenized terms rather than arbitrary substrings or typo variants. 
Those limits are acceptable for the current product catalog; 
multilingual, fuzzy, or advanced faceted search would call for additional indexing or a dedicated search system. 
Search results currently have no explicit pagination or rank threshold.



Configuration notes

DEBUG is enabled in the checked-in settings and ALLOWED_HOSTS is empty. 
These defaults are suitable only for local development and must be configured for a deployed environment. Keep .env and database credentials out of version control.

Sales report endpoint -

api/v1/reports/sales/
It reports the count and total revenue for confirmed orders, plus quantity sold and line revenue grouped by product. 
You can optionally filter with inclusive start_date and end_date parameters in YYYY-MM-DD format.
Invalid dates or a start date after the end date return 400.
The report calculates each product’s revenue as unit_price × quantity, then sums those line revenues for the overall total.

A load test sends several requests at once to check two things:

The script tests two things at once: whether concurrent orders can oversell one product, 
and whether sales-report requests still finish while those orders are running.

Command-line arguments: 
--product-id selects the test product; 
--attempts sets the number of order requests;
--reports sets the number of report requests; 
--workers sets the maximum number of requests running at once. 
--base-url defaults to the local Django server.

Concurrent load test: 
With a disposable product starting at stock 25, 
I ran 
python load_test.py --product-id 5 --attempts 100 --reports 10 --workers 20 

against the local Django server and PostgreSQL database. 
The run returned 25 successful orders, 75 stock-related rejections, and final stock 0. 
All 10 report requests returned successfully.
Measured latency was p50 0.051s and p95 0.541s. No unexpected order statuses or failed reports occurred.

Run the full stack with Docker Compose

Prerequisite: install and start Docker Desktop (or Docker Engine with the Compose plugin). From the repository root, run:

docker compose up --build

Compose builds the Django image, starts PostgreSQL, waits for its health check, applies Django migrations, and starts the API at http://127.0.0.1:8000/. The PostgreSQL data is kept in the named Docker volume `postgres_data_v2`.

The Compose file has development-only fallback credentials so the command works without a local `.env` file. To override them, create an ignored `.env` file using the variable names shown below. Do not use these local defaults outside a disposable development environment.

How Docker Compose works

Docker Compose builds the Django application image from the Dockerfile and runs the application and PostgreSQL in separate containers.
It waits for PostgreSQL's health check before starting Django. 
The application connects to the database using the Compose service name db and the database settings supplied as environment variables. 
On startup, Django applies migrations and then serves the API on port 8000, available from the host at http://127.0.0.1:8000/. 
PostgreSQL stores its data in the `postgres_data_v2` named volume, which persists when the containers stop. 
This makes the local environment repeatable without installing Python dependencies or PostgreSQL directly on the host.
