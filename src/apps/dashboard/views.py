"""Dashboard: the page (the React build) and its read-only JSON API.

    GET /dashboard/                                  the page (login required)
  main view
    GET /api/dashboard/summary/                      the run, the matched restaurants, venues per match group
    GET /api/dashboard/venues/?group=&page=          venues of a match group, 25 per page
    GET /api/dashboard/categories/?family=&level=&order=&top=
    GET /api/dashboard/categories/detail/?level=&key=
  "more detail" (asked for only when the section is unfolded)
    GET /api/dashboard/dishes/?group=&page=          dishes of the accepted or confirmed venues, 25 per page
    GET /api/dashboard/menus/ | quality/

Every API response is about the last published run; without one, it is a 404. The answers come from
DashboardService, one method per chart, and go out through their response serializer (serializers.py): the
contract the frontend's schemas.ts mirrors.
"""

from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.dashboard.constants import PAGE_SIZE
from apps.dashboard.dashboard_services import CategoryNotFoundError, DashboardService
from apps.dashboard.permissions import can_view_dashboard
from apps.dashboard.serializers import (
    CategoriesParams,
    CategoryDetailParams,
    CategoryDetailSerializer,
    CategoryRowSerializer,
    DishesParams,
    DishRowSerializer,
    MenusSerializer,
    QualitySerializer,
    SummarySerializer,
    VenueRowSerializer,
    VenuesParams,
)
from apps.pipeline.models import PipelineRun


def _can_view_or_403(user) -> bool:
    if not can_view_dashboard(user):
        raise PermissionDenied
    return True


@require_GET
@login_required
@user_passes_test(_can_view_or_403)
@ensure_csrf_cookie  # the page logs out with a POST
def dashboard_page(request):
    index = Path(settings.DASHBOARD_INDEX_FILE)
    if not index.is_file():
        return HttpResponse("El frontend no está compilado: cd frontend && npm ci && npm run build",
                            status=503, content_type="text/plain; charset=utf-8")
    return HttpResponse(index.read_bytes(), content_type="text/html; charset=utf-8")


class DashboardAPIView(APIView):
    http_method_names = ["get"]

    def service(self) -> DashboardService:
        run = PipelineRun.objects.last_published()
        if run is None:
            raise NotFound("Todavía no hay corridas terminadas.")
        return DashboardService(run)

    @staticmethod
    def params(serializer_class, request) -> dict:
        serializer = serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class ListPagination(PageNumberPagination):
    page_size = PAGE_SIZE

    def paginated(self, rows, serializer_class, view) -> Response:
        """One page of `rows`, each written by `serializer_class`: {count, next, previous, results}."""
        page = self.paginate_queryset(rows, view.request, view=view)
        return self.get_paginated_response(serializer_class(page, many=True).data)


# --- main view --------------------------------------------------------------------------------------------


class SummaryView(DashboardAPIView):
    """What the page shows first: the run, the matched restaurants and the venues per match group."""

    def get(self, request):
        service = self.service()
        return Response(SummarySerializer({"run": service.run_info(), "matched": service.matched_restaurants(),
                                           "match_groups": service.match_groups()}).data)


class VenuesView(DashboardAPIView):
    def get(self, request):
        venues = self.service().venues(**self.params(VenuesParams, request))
        return ListPagination().paginated(venues, VenueRowSerializer, view=self)


class CategoriesView(DashboardAPIView):
    def get(self, request):
        categories = self.service().top_categories(**self.params(CategoriesParams, request))
        return Response(CategoryRowSerializer(categories, many=True).data)


class CategoryDetailView(DashboardAPIView):
    def get(self, request):
        try:
            detail = self.service().category_detail(**self.params(CategoryDetailParams, request))
        except CategoryNotFoundError:
            raise NotFound("Categoría desconocida.") from None
        return Response(CategoryDetailSerializer(detail).data)


# --- "more detail" ----------------------------------------------------------------------------------------


class DishesView(DashboardAPIView):
    def get(self, request):
        dishes = self.service().dishes(**self.params(DishesParams, request))
        return ListPagination().paginated(dishes, DishRowSerializer, view=self)


class MenusView(DashboardAPIView):
    def get(self, request):
        return Response(MenusSerializer(self.service().menus()).data)


class QualityView(DashboardAPIView):
    def get(self, request):
        return Response(QualitySerializer(self.service().quality()).data)
