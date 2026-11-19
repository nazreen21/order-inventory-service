import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor 
from threading import Event
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def send(method, url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )

    started = time.perf_counter()
    try:
        with urlopen(request, timeout=15) as response:
            status = response.status
            body = response.read().decode()
    except HTTPError as error:
        status = error.code
        body = error.read().decode()
    except URLError as error:
        status = 0
        body = str(error.reason)

    elapsed = time.perf_counter() - started
    return status, elapsed, body


def percentile(values, percent):
    ordered = sorted(values)
    index = min(int(len(ordered) * percent), len(ordered) - 1)
    return ordered[index]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--product-id", type=int, required=True)
    parser.add_argument("--attempts", type=int, default=100)
    parser.add_argument("--reports", type=int, default=10)
    parser.add_argument("--workers", type=int, default=20)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    product_url = f"{base}/api/v1/products/{args.product_id}/"
    order_url = f"{base}/api/v1/orders/"
    report_url = f"{base}/api/v1/reports/sales/"

    status, _, body = send("GET", product_url)
    if status != 200:
        raise SystemExit(f"Could not read product: HTTP {status}: {body}")

    initial_stock = json.loads(body)["stock"]
    if args.attempts <= initial_stock:
        raise SystemExit(
            f"Use more attempts than stock to test overselling. "
            f"Stock={initial_stock}, attempts={args.attempts}"
        )

    gate = Event()

    def place_one_order():
        gate.wait()
        return send(
            "POST",
            order_url,
            {"items": [{"product_id": args.product_id, "quantity": 1}]},
        )

    def request_report():
        gate.wait()
        return send("GET", report_url)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(place_one_order) for _ in range(args.attempts)
        ]
        futures.extend(
            pool.submit(request_report) for _ in range(args.reports)
        )

        # Let the queued workers begin together.
        gate.set()
        results = [future.result() for future in futures]

    order_results = results[:args.attempts]
    report_results = results[args.attempts:]

    successful_orders = sum(status == 201 for status, _, _ in order_results)
    rejected_orders = sum(status == 400 for status, _, _ in order_results)
    unexpected_orders = [
        (status, body)
        for status, _, body in order_results
        if status not in (201, 400)
    ]
    failed_reports = [
        (status, body)
        for status, _, body in report_results
        if status != 200
    ]

    status, _, body = send("GET", product_url)
    if status != 200:
        raise SystemExit(f"Could not read final stock: HTTP {status}: {body}")

    final_stock = json.loads(body)["stock"]
    expected_stock = max(initial_stock - args.attempts, 0)
    expected_successes = min(initial_stock, args.attempts)

    latencies = [elapsed for _, elapsed, _ in results]
    print(f"Initial stock:     {initial_stock}")
    print(f"Successful orders: {successful_orders}")
    print(f"Rejected orders:   {rejected_orders}")
    print(f"Final stock:       {final_stock} (expected {expected_stock})")
    print(f"Report requests:   {len(report_results) - len(failed_reports)} "
          f"successful / {len(report_results)} total")
    print(f"Latency p50:       {statistics.median(latencies):.3f}s")
    print(f"Latency p95:       {percentile(latencies, 0.95):.3f}s")
    print(f"Unexpected orders: {unexpected_orders[:3]}")
    print(f"Failed reports:    {failed_reports[:3]}")

    if (
        successful_orders != expected_successes
        or final_stock != expected_stock
        or unexpected_orders
        or failed_reports
    ):
        raise SystemExit("LOAD TEST FAILED")
    print("LOAD TEST PASSED")


if __name__ == "__main__":
    main()