"""Project-wide pagination.

DRF's ``PageNumberPagination`` hard-codes ``page_size_query_param = None`` as a
class attribute — unlike ``PAGE_SIZE``, it is not read from the
``REST_FRAMEWORK`` settings dict, so a client cannot ask for a larger page
without a subclass. Without one, ``PAGE_SIZE = 20`` silently truncated every
list endpoint: the department picker saw only 20 of 51 units, and calls that
already passed ``?page_size=100`` were quietly ignored.
"""
from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """Paginate at 20, but let clients ask for more via ``?page_size=``.

    ``max_page_size`` is generous because several screens legitimately need a
    whole reference table at once — the organisation chart, the directorate
    switcher, and the audit-universe pickers. It still caps the damage a stray
    ``?page_size=999999`` can do.
    """

    page_size_query_param = 'page_size'
    max_page_size = 1000
