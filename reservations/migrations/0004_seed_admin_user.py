from django.contrib.auth.hashers import make_password
from django.db import migrations


def create_admin(apps, schema_editor):
    User = apps.get_model("auth", "User")
    admin, created = User.objects.get_or_create(
        username="admin",
        defaults={
            "email": "admin@rezervem.com",
            "is_staff": True,
            "is_superuser": True,
            "password": make_password("Admin12345"),
        },
    )
    if not created:
        admin.is_staff = True
        admin.is_superuser = True
        admin.email = admin.email or "admin@rezervem.com"
        admin.password = make_password("Admin12345")
        admin.save()


def remove_admin(apps, schema_editor):
    User = apps.get_model("auth", "User")
    User.objects.filter(username="admin").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0003_restaurant_concept"),
    ]

    operations = [
        migrations.RunPython(create_admin, remove_admin),
    ]
