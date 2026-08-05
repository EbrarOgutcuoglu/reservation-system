from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("reservations", "0004_seed_admin_user"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReservationHold",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("slot", models.CharField(max_length=20)),
                ("expires_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reservation_holds",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="reservationhold",
            constraint=models.UniqueConstraint(fields=("date", "slot"), name="unique_reservation_hold_slot"),
        ),
        migrations.AddIndex(
            model_name="reservationhold",
            index=models.Index(fields=["user"], name="reservatio_user_id_59ba0f_idx"),
        ),
        migrations.AddIndex(
            model_name="reservationhold",
            index=models.Index(fields=["expires_at"], name="reservatio_expires_0f8000_idx"),
        ),
    ]
