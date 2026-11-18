
from django.db import models
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex


class Product(models.Model):

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10,decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    search_vector = SearchVectorField(null=True, editable=False)

    class Meta:
        indexes = [
        models.Index(fields=["name"]),
        models.Index(fields=["is_active"]),
        GinIndex(
            fields=["search_vector"],
            name="product_search_gin",
        ),
    ]

    def __str__(self):
        return self.name
