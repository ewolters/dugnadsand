"""Admit a vetted organization.

Deliberately a command and not a web form. Admission is a decision somebody
makes about a real organization after talking to them — the login page says as
much ("admission is a conversation, not a button") — and a self-serve signup
would make that untrue.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from site_app.models import Organization
from site_app.tenancy import bypass_rls


class Command(BaseCommand):
    help = "Admit a vetted mutual aid organization."

    def add_arguments(self, parser):
        parser.add_argument("name", help='Display name, e.g. "Rivertown Mutual Aid"')
        parser.add_argument(
            "--slug", help="URL-safe short name; derived from the name if omitted")

    def handle(self, *args, **options):
        name = options["name"].strip()
        slug = slugify(options["slug"] or name)
        if not slug:
            raise CommandError("Could not derive a slug; pass --slug explicitly.")

        # Organization is not tenant-scoped, so this would work without the
        # bypass. It is here to say plainly that admission happens outside any
        # one organization's view of the world.
        with bypass_rls():
            if Organization.objects.filter(slug=slug).exists():
                raise CommandError(
                    f"An organization with slug '{slug}' is already admitted.")
            org = Organization.objects.create(slug=slug, name=name)

        self.stdout.write(self.style.SUCCESS(f"Admitted {org.name} ({org.slug})."))
        self.stdout.write(
            "Add its first member with:\n"
            f'  manage.py add_member {org.slug} <username> "<display name>"')
