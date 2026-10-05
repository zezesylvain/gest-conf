"""Pagination uniforme de l'API (plan L1 §9.1)."""

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Pagination par numéro de page : 25 éléments par défaut, 100 au plus.

    Paramètres de requête : ``page`` et ``page_size`` (plafonné à ``max_page_size``).
    Le tri reste à la charge de chaque vue, toujours explicite et déterministe
    (départage par ``id``), faute de quoi les pages se recouvrent.
    """

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
