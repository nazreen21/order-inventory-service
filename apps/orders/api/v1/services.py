from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.products.models import Product
from apps.orders.models import Order, OrderItem


@transaction.atomic
def place_order(items):

    #Combine duplicate product IDs
    quantities = {}

    for item in items:
        product_id = item["product_id"]
        quantity = item["quantity"]

        quantities[product_id] = (
            quantities.get(product_id, 0) + quantity
        )

    # Lock product rows in consistent order
    product_ids = sorted(quantities.keys())

    products = list(
        Product.objects
        .select_for_update()
        .filter(id__in=product_ids)
        .order_by("id")
    )

    product_map = {
        product.id: product
        for product in products
    }

    # Validate all products before changing stock
    if len(product_map) != len(product_ids):
        raise ValidationError("One or more products do not exist.")

    total_amount = 0
    order_items = []

    for product_id, quantity in quantities.items():

        product = product_map[product_id]

        if not product.is_active:
            raise ValidationError(
                f"{product.name} is not available."
            )

        if product.stock < quantity:
            raise ValidationError(
                f"Insufficient stock for {product.name}. "
                f"Available: {product.stock}, Requested: {quantity}"
            )

        total_amount += product.price * quantity

        # Prepare stock updates
        product.stock -= quantity

        # Prepare order items
        order_items.append(
            OrderItem(
                product=product,
                quantity=quantity,
                unit_price=product.price
            )
        )

    #Update inventory
    Product.objects.bulk_update(
        list(product_map.values()),
        ["stock"]
    )

    #Create order
    order = Order.objects.create(
        status=Order.Status.CONFIRMED,
        total_amount=total_amount
    )

    #Create order items
    for item in order_items:
        item.order = order

    OrderItem.objects.bulk_create(order_items)

    return order