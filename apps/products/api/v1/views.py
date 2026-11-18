from django.db.models import Q
from django.db import connection
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.products.models import Product
from .serializers import ProductSerializer


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    queryset = Product.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "list":
            qs = qs.filter(is_active=True)
        return qs





