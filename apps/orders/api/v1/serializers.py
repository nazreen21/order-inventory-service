
from rest_framework import serializers
from apps.orders.models import Order, OrderItem


class OrderItemInputSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class OrderCreateSerializer(serializers.Serializer):
    items = OrderItemInputSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError(
                "At least one item is required."
            )

        return value


class OrderItemResponseSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name",read_only=True)
    subtotal = serializers.DecimalField(max_digits=12,decimal_places=2,read_only=True)

    class Meta:
        model = OrderItem

        fields = ["product","product_name","quantity","unit_price","subtotal"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemResponseSerializer(many=True)

    class Meta:
        model = Order

        fields = ["id","status","total_amount","items","created_at"]
