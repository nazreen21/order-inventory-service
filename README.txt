Order Inventory Service

A Django REST Framework API for product inventory, order placement, and PostgreSQL-backed product search.

Setup and run

From the repository root, create and activate a virtual environment, then install dependencies:

Activate virtual environment

py -m venv .venv
.\.venv\Scripts\Activate.ps1


Create a PostgreSQL database and role, then add a .env file in the repository root. The application loads this file through python-dotenv:

.env contains credentials :-

SECRET_KEY=replace-with-a-local-secret
DB_NAME=order_inventory
DB_USER=order_inventory_user
DB_PASSWORD=replace-with-your-database-password
DB_HOST=localhost
DB_PORT=5432


Apply migrations and start Django's development server:

python manage.py migrate
python manage.py runserver

The server is available at 'http://127.0.0.1:8000/'. The Django admin is at /admin/; create an admin account with python manage.py createsuperuser if needed. 
Product records can be managed through the product API or admin.

API overview

All API routes use the /api/v1/ prefix.


GET  /api/v1/products/ ->  List active products 
POST  /api/v1/products/ -> Create a product 
GET, PUT, PATCH, DELETE  /api/v1/products/{id}/  Retrieve or manage a product 
GET /api/v1/products/search/?q=laptop -> Search active products by name and description, ordered by relevance 
POST /api/v1/orders/ -> Place an order and decrement inventory atomically 
GET -> /api/v1/orders/{id}/ -> Retrieve an order with its items 
GET /api/v1/reports/sales/ -> Aggregate confirmed order count, revenue, and per-product sales

Order creation expects a non-empty items array. Each entry contains an integer product_id and a positive integer quantity.
 Duplicate product IDs are combined before stock validation. Successful creation returns 201; invalid or unavailable products and insufficient stock return 400.

The sales report optionally accepts inclusive `start_date` and `end_date` query parameters in `YYYY-MM-DD` format. It returns the confirmed order count and total revenue, along with units sold and line revenue grouped by product. Invalid dates or a start date after the end date return 400. Example: `/api/v1/reports/sales/?start_date=2026-01-01&end_date=2026-01-31`.

Example:
{
  "items": [
    {"product_id": 1, "quantity": 2},
    {"product_id": 3, "quantity": 1}
  ]
}

Architecture

- core/ contains Django settings and root URL routing. It mounts versioned order, product, and report APIs.
- apps/products/ owns the product model and product API. Its model holds stock, price, active status, and the search vector.
- apps/orders/ owns order and order-item models, request/response serializers, API views, and the place_order service. 
  The service encapsulates the inventory and order write as one transaction.
- apps/reports/ contains the async sales report endpoint and its URL configuration. Its ORM aggregation runs in Django's thread-sensitive sync bridge so synchronous ORM work does not block the event loop.
- apps/*/migrations/ contains schema changes. The product search migration adds the search vector and GIN index.

The API is organized by domain app and versioned URL namespace. DRF serializers validate input and shape output; views handle HTTP concerns; order business rules live in the service layer.

Connection handling and concurrency

Database access uses Django's PostgreSQL backend and psycopg 3. Connection parameters come from environment variables loaded from .env for local development. 
Django manages connections through its request lifecycle; 
this project does not configure persistent connections (`CONN_MAX_AGE`) or a separate pooler. This keeps the deployment model simple and avoids keeping idle connections open by default, at the cost of connection setup overhead under sustained traffic. For production, size the application worker count against PostgreSQL's connection limit and consider a managed pooler or explicitly configured persistent connections when measured workload justifies it.

Order placement runs inside `transaction.atomic`. It combines duplicate product lines, locks the affected product rows with select_for_update() in ascending ID order, 
validates all stock and active-state conditions, then updates inventory and creates the order/items.
The row locks prevent concurrent orders from both consuming the same available stock; a consistent lock order reduces deadlock risk when orders overlap. 
The transaction means a validation or database failure rolls back the whole operation. 
This uses blocking row locks, so heavily contended products can make requests wait. 
It favors correctness and straightforward Django behavior over a more complex conditional-update or queue-based design.

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

ThreadPoolExecutor runs multiple requests concurrently using a pool of threads. 
Event releases the waiting workers; 
and urllib sends HTTP requests.

send(method, url, payload=None): Builds and sends one HTTP request. 
It records how long it takes and returns the HTTP status, elapsed time, and response body. 
HTTP errors such as 400 are recorded as responses; connection errors are returned with status 0.

percentile(values, percent): Sorts the measured request times and selects a value near the requested percentile.
The p95 is a useful way to describe the slower end of this run’s response times.

Command-line arguments: 
--product-id selects the test product; 
--attempts sets the number of order requests;
--reports sets the number of report requests; 
--workers sets the maximum number of requests running at once. 
--base-url defaults to the local Django server.

Concurrent load test: 
With a disposable product starting at stock 25, 
I ran python load_test.py --product-id 5 --attempts 100 --reports 10 --workers 20 against the local Django server and PostgreSQL database. 
The run returned 25 successful orders, 75 stock-related rejections, and final stock 0. 
All 10 report requests returned successfully.
Measured latency was p50 0.051s and p95 0.541s. No unexpected order statuses or failed reports occurred.

Run the full stack with Docker Compose

Prerequisite: install and start Docker Desktop (or Docker Engine with the Compose plugin). From the repository root, run:

docker compose up --build

Compose builds the Django image, starts PostgreSQL, waits for its health check, applies Django migrations, and starts the API at http://127.0.0.1:8000/. The PostgreSQL data is kept in the named Docker volume `postgres_data_v2`.

The Compose file has development-only fallback credentials so the command works without a local `.env` file. To override them, create an ignored `.env` file using the variable names shown below. Do not use these local defaults outside a disposable development environment.

How Docker Compose works

Docker Compose builds the Django application image from the Dockerfile and runs the application and PostgreSQL in separate containers. It waits for PostgreSQL's health check before starting Django. The application connects to the database using the Compose service name `db` and the database settings supplied as environment variables. On startup, Django applies migrations and then serves the API on port 8000, available from the host at http://127.0.0.1:8000/. PostgreSQL stores its data in the `postgres_data` named volume, which persists when the containers stop. This makes the local environment repeatable without installing Python dependencies or PostgreSQL directly on the host.
