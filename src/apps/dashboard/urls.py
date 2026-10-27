from django.contrib.auth import views as auth_views
from django.urls import path
from django.views.generic import RedirectView

from apps.dashboard import views
from apps.dashboard.login import LoginView

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="dashboard", permanent=False)),
    path("dashboard/", views.dashboard_page, name="dashboard"),
    path("accounts/login/", LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("api/dashboard/summary/", views.SummaryView.as_view(), name="dashboard-summary"),
    path("api/dashboard/categories/", views.CategoriesView.as_view(), name="dashboard-categories"),
    path("api/dashboard/categories/detail/", views.CategoryDetailView.as_view(), name="dashboard-category"),
    path("api/dashboard/venues/", views.VenuesView.as_view(), name="dashboard-venues"),
    path("api/dashboard/dishes/", views.DishesView.as_view(), name="dashboard-dishes"),
    path("api/dashboard/menus/", views.MenusView.as_view(), name="dashboard-menus"),
    path("api/dashboard/quality/", views.QualityView.as_view(), name="dashboard-quality"),
]
