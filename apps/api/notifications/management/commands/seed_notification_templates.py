from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from notifications.services import seed_default_templates


class Command(BaseCommand):
    help = "Seed versioned Arabic and English notification templates"

    @transaction.atomic
    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        count = seed_default_templates()
        self.stdout.write(self.style.SUCCESS(f"Notification templates ready: {count}"))
