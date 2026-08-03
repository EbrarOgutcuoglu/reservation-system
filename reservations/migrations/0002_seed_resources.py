from django.db import migrations


def create_resources(apps, schema_editor):
    Resource = apps.get_model("reservations", "Resource")
    items = [
        ("Meeting Room", "A small room for team meetings."),
        ("Restaurant Table", "Table for lunch or dinner reservation."),
        ("Tennis Court", "Outdoor court for one hour sport sessions."),
    ]
    for name, description in items:
        Resource.objects.get_or_create(
            name=name,
            defaults={"description": description, "is_active": True},
        )


def delete_resources(apps, schema_editor):
    Resource = apps.get_model("reservations", "Resource")
    Resource.objects.filter(
        name__in=["Meeting Room", "Restaurant Table", "Tennis Court"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_resources, delete_resources),
    ]
