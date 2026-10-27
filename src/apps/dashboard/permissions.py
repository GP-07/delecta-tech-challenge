"""Who sees the dashboard: active users with read access to the pipeline results, i.e. the "Dashboard" group
(created by migration 0001) or superusers. Seeing the dashboard never allows changing anything."""

from rest_framework.permissions import BasePermission

from apps.dashboard.constants import DASHBOARD_PERMISSIONS


def can_view_dashboard(user) -> bool:
    return user.is_active and user.has_perms(DASHBOARD_PERMISSIONS)


class CanViewDashboard(BasePermission):
    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated and can_view_dashboard(request.user))
