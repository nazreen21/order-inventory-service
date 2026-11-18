
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import F
from apps.products.models import Product
from apps.orders.models import Order, OrderItem


@transaction.atomic
def place_order(items):

    # Combine duplicate product IDs.
    quantities = {}

    for item in items:
        product_id = item["product_id"]
        quantity = item["quantity"]

        if quantity <= 0:
            raise ValidationError(
                "Quantity must be greater than zero."
            )

        quantities[product_id] = (
            quantities.get(product_id, 0) + quantity
        )

    product_ids = sorted(quantities.keys())

    # Lock rows in a consistent order to reduce deadlocks.
    products = list(
        Product.objects.select_for_update()
        .filter(
            id__in=product_ids,
            is_active=True
        )
        .order_by("id")
    )

    # Ensure every requested product exists.
    if len(products) != len(product_ids):
        raise ValidationError(
            "One or more products do not exist or are inactive."
        )

    total_amount = 0
    order_items = []

    # Validate stock before changing anything.
    for product in products:

        quantity = quantities[product.id]

        

        if product.stock < quantity:
            raise ValidationError(
                f"Insufficient stock for {product.name}. "
                f"Available: {product.stock}"
            )

        total_amount += product.price * quantity

        order_items.append(
            OrderItem(
                product=product,
                quantity=quantity,
                unit_price=product.price
            )
        )

    # Create the order.
    order = Order.objects.create(
        total_amount=total_amount,
        status=Order.Status.CONFIRMED
    )

    # Reduce stock and create order items.
    for product, order_item in zip(products, order_items):

        quantity = quantities[product.id]

        Product.objects.filter(
            id=product.id
        ).update(
            stock=F("stock") - quantity
        )

        order_item.order = order
        order_item.save()

    return order
