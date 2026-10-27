import pytest
from django.urls import reverse

from apps.menus.models import FoodCategory, MenuItem, Method
from tests.conftest import TIFLIS_ID
from tests.runs import published_run

pytestmark = pytest.mark.django_db


@pytest.fixture
def items(tiflis_expected):
    published_run({TIFLIS_ID: tiflis_expected})
    return MenuItem.objects.all()


def test_staff_correct_the_category_of_an_item_and_nothing_else(admin_client, admin_user, items):
    odjakhuri = items.get(name="Odjakhuri")
    pork = FoodCategory.objects.get(name="pork")

    response = admin_client.post(reverse("admin:menus_menuitem_change", args=[odjakhuri.pk]),
                                 {"category": pork.pk, "name": "Changed by hand"})

    assert response.status_code == 302
    odjakhuri.refresh_from_db()
    assert (odjakhuri.category, odjakhuri.method, odjakhuri.reviewed_by, odjakhuri.name) == (
        pork, Method.MANUAL, admin_user, "Odjakhuri")


@pytest.mark.parametrize(("query", "shown", "hidden"), [
    ("confianza=sin", "Odjakhuri", "Ensalada Georgiana"),
    ("confianza=baja", "Pkhali Mix", "Ensalada Georgiana"),
    ("category__parent=salads", "Ensalada Georgiana", "Odjakhuri"),
])
def test_items_can_be_filtered_by_confidence_and_category(admin_client, items, query, shown, hidden):
    response = admin_client.get(reverse("admin:menus_menuitem_changelist") + "?" + query)

    content = response.content.decode()
    assert response.status_code == 200
    assert shown in content and hidden not in content


def test_items_and_categories_cannot_be_added_from_the_admin(admin_client, items):
    assert admin_client.get(reverse("admin:menus_menuitem_add")).status_code == 403
    assert admin_client.get(reverse("admin:menus_foodcategory_add")).status_code == 403
