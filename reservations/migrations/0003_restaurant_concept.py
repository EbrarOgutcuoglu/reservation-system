from django.db import migrations


def switch_to_restaurant(apps, schema_editor):
    Resource = apps.get_model("reservations", "Resource")
    Resource.objects.get_or_create(
        name="Rezervem Restaurant",
        defaults={
            "description": "Restaurant table reservation area.",
            "is_active": True,
        },
    )
    Resource.objects.filter(
        name__in=["Meeting Room", "Restaurant Table", "Tennis Court"]
    ).update(is_active=False)


def restore_old_resources(apps, schema_editor):
    Resource = apps.get_model("reservations", "Resource")
    Resource.objects.filter(
        name__in=["Meeting Room", "Restaurant Table", "Tennis Court"]
    ).update(is_active=True)


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0002_seed_resources"),
    ]

    operations = [
        migrations.RunPython(switch_to_restaurant, restore_old_resources),
    ]
