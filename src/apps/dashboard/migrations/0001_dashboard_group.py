"""The "Dashboard" group: read-only access to the pipeline results. Add users to it in the admin."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP = "Dashboard"
PERMISSIONS = [  # (app label, codename); kept here, not imported, so the migration never changes
    ("pipeline", "view_pipelinerun"),
    ("venues", "view_venue"),
    ("venues", "view_venuematch"),
    ("menus", "view_menuitem"),
    ("menus", "view_foodcategory"),
]


def create_group(apps, schema_editor):
    for label in {label for label, _ in PERMISSIONS}:  # on a new database they are only created after migrating
        app_config = apps.get_app_config(label)
        app_config.models_module = True  # the migration's app stub has none; create_permissions skips those
        create_permissions(app_config, verbosity=0, apps=apps)
        app_config.models_module = None
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group, _ = Group.objects.get_or_create(name=GROUP)
    for label, codename in PERMISSIONS:
        group.permissions.add(Permission.objects.get(content_type__app_label=label, codename=codename))


def delete_group(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name=GROUP).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("pipeline", "0001_initial"),
        ("venues", "0001_initial"),
        ("menus", "0001_initial"),
    ]

    operations = [migrations.RunPython(create_group, delete_group)]
