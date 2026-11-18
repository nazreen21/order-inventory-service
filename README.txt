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

Order creation expects a non-empty `items` array. Each entry contains an integer `product_id` and a positive integer `quantity`.
 Duplicate product IDs are combined before stock validation. Successful creation returns `201`; invalid or unavailable products and insufficient stock return `400`.

Example:

```json
{
  "items": [
    {"product_id": 1, "quantity": 2},
    {"product_id": 3, "quantity": 1}
  ]
}
```

## Architecture

- `core/` contains Django settings and root URL routing. It mounts versioned order and product APIs.
- `apps/products/` owns the product model and product API. Its model holds stock, price, active status, and the search vector.
- `apps/orders/` owns order and order-item models, request/response serializers, API views, and the `place_order` service. The service encapsulates the inventory and order write as one transaction.
- `apps/reports/` contains reporting-related app code; no report endpoint is mounted in the current root URL configuration.
- `apps/*/migrations/` contains schema changes. The product search migration adds the search vector and GIN index.

The API is organized by domain app and versioned URL namespace. DRF serializers validate input and shape output; views handle HTTP concerns; order business rules live in the service layer.

## Connection handling and concurrency

Database access uses Django's PostgreSQL backend and psycopg 3. Connection parameters come from environment variables loaded from `.env` for local development. Django manages connections through its request lifecycle; this project does not configure persistent connections (`CONN_MAX_AGE`) or a separate pooler. This keeps the deployment model simple and avoids keeping idle connections open by default, at the cost of connection setup overhead under sustained traffic. For production, size the application worker count against PostgreSQL's connection limit and consider a managed pooler or explicitly configured persistent connections when measured workload justifies it.

Order placement runs inside `transaction.atomic`. It combines duplicate product lines, locks the affected product rows with `select_for_update()` in ascending ID order, validates all stock and active-state conditions, then updates inventory and creates the order/items. The row locks prevent concurrent orders from both consuming the same available stock; a consistent lock order reduces deadlock risk when orders overlap. The transaction means a validation or database failure rolls back the whole operation. This uses blocking row locks, so heavily contended products can make requests wait. It favors correctness and straightforward Django behavior over a more complex conditional-update or queue-based design.

## Search design and trade-offs

Product search uses PostgreSQL full-text search rather than substring matching or an external search service. `Product.search_vector` stores preprocessed tokens, and a GIN index supports matching at scale. A database trigger maintains the vector when product name or description changes, including updates made outside Django; a migration backfills existing rows. The search API parses input with PostgreSQL's English `websearch` query syntax and ranks matching active products with `SearchRank`.

This keeps search and product data in the same database, avoids operating another service, and provides stemming, query syntax, indexed matching, and relevance ordering. The English text configuration is language-specific, and full-text search matches tokenized terms rather than arbitrary substrings or typo variants. Those limits are acceptable for the current product catalog; multilingual, fuzzy, or advanced faceted search would call for additional indexing or a dedicated search system. Search results currently have no explicit pagination or rank threshold.

## Configuration notes

`DEBUG` is enabled in the checked-in settings and `ALLOWED_HOSTS` is empty. These defaults are suitable only for local development and must be configured for a deployed environment. Keep `.env` and database credentials out of version control.
