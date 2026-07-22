# Generated for G12 platform administration and reporting.
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("organizations", "0002_verification_branches_and_payouts"),
    ]

    operations = [
        migrations.CreateModel(
            name="OfficeStatusAction",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("previous_status", models.CharField(max_length=24)),
                ("new_status", models.CharField(max_length=24)),
                ("reason", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.RESTRICT,
                        related_name="office_status_actions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "office",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.RESTRICT,
                        related_name="status_actions",
                        to="organizations.office",
                    ),
                ),
            ],
            options={"db_table": "office_status_actions", "ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="officestatusaction",
            index=models.Index(fields=["office", "-created_at"], name="ix_office_status_history"),
        ),
    ]
