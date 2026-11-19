from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.products.models import Product
from .serializers import ProductSerializer
from rest_framework.exceptions import ValidationError
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import F


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    queryset = Product.objects.all().order_by("-created_at", "-id")

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action in ["list", "search"]:
            qs = qs.filter(is_active=True)
        return qs

    @action(detail=False, methods=["get"])
    def search(self, request):

        query = request.query_params.get("q", "").strip()

        if not query:
            raise ValidationError({
                "q": "Search query is required."
            })

        search_query = SearchQuery(
            query,
            search_type="websearch",
            config="english"
        )

        products = (
            self.get_queryset()
            .filter(search_vector=search_query)
            .annotate(
                rank=SearchRank(
                    F("search_vector"),
                    search_query
                )
            )
            .order_by("-rank")
        )

        serializer = self.get_serializer(products, many=True)

        return Response(serializer.data)