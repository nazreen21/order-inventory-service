from django.core.exceptions import ValidationError
from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import Order
from .serializers import OrderCreateSerializer,OrderSerializer
from .services import place_order


class CreateOrderView(APIView):

    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:

            order = place_order(
                serializer.validated_data["items"]
            )
            response_data = OrderSerializer(order).data

            return Response(
                response_data,
                status=status.HTTP_201_CREATED
            )

        except ValidationError as exc:

            return Response(
                {"error": exc.messages},
                status=status.HTTP_400_BAD_REQUEST
            )


class OrderDetailView(generics.RetrieveAPIView):
    queryset = Order.objects.prefetch_related("items__product")
    serializer_class = OrderSerializer
