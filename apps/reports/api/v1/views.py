from decimal import Decimal

from asgiref.sync import sync_to_async
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.http import JsonResponse
from django.utils.dateparse import parse_date

from apps.orders.models import Order, OrderItem


def _build_sales_report(start_date, end_date):
    orders = Order.objects.filter(status=Order.Status.CONFIRMED)
    items = OrderItem.objects.filter(order__status=Order.Status.CONFIRMED)

    if start_date:
        orders = orders.filter(created_at__date__gte=start_date)
        items = items.filter(order__created_at__date__gte=start_date)
    if end_date:
        orders = orders.filter(created_at__date__lte=end_date)
        items = items.filter(order__created_at__date__lte=end_date)

    summary = orders.aggregate(
        order_count=Count("id"),
        revenue=Sum("total_amount"),
    )
    # Sum each line's captured unit price multiplied by its quantity.
    product_rows = items.values(
        "product_id", "product__name"
    ).annotate(
        quantity_sold=Sum("quantity"),
        revenue=Sum(ExpressionWrapper(
            F("unit_price") * F("quantity"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )),
    ).order_by("-quantity_sold", "product_id")

    return {
        "period": {
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        },
        "order_count": summary["order_count"],
        "revenue": str(summary["revenue"] or Decimal("0.00")),
        "products": [
            {
                "product_id": row["product_id"],
                "name": row["product__name"],
                "quantity_sold": row["quantity_sold"],
                "revenue": str(row["revenue"] or Decimal("0.00")),
            }
            for row in product_rows
        ],
    }


async def sales_report(request):
    # Aggregate confirmed orders, optionally bounded by inclusive dates.
    raw_start = request.GET.get("start_date")
    raw_end = request.GET.get("end_date")
    start_date = parse_date(raw_start) if raw_start else None
    end_date = parse_date(raw_end) if raw_end else None

    if raw_start and start_date is None:
        return JsonResponse({"error": "start_date must use YYYY-MM-DD."}, status=400)
    if raw_end and end_date is None:
        return JsonResponse({"error": "end_date must use YYYY-MM-DD."}, status=400)
    if start_date and end_date and start_date > end_date:
        return JsonResponse(
            {"error": "start_date must be on or before end_date."}, status=400
        )

    data = await sync_to_async(_build_sales_report, thread_sensitive=True)(
        start_date, end_date
    )
    return JsonResponse(data)
