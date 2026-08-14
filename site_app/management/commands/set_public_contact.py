"""Publish how a group can be reached, and what it does.

Blank means unlisted. A group appears on /need-help/ only once somebody has
deliberately said how to reach it — publishing a route to a group's door is a
decision they make rather than a default they discover.
"""

from django.core.management.base import BaseCommand, CommandError

from site_app.models import Organization
from site_app.tenancy import bypass_rls


class Command(BaseCommand):
    help = "Set the public contact and description for an organization."

    def add_arguments(self, parser):
        parser.add_argument("slug")
        parser.add_argument("--contact", default=None,
                            help="How to reach them, in their own words")
        parser.add_argument("--serves", default=None,
                            help="What they do and who they serve")
        parser.add_argument("--unlist", action="store_true",
                            help="Clear the contact, removing them from the page")

    def handle(self, *args, **options):
        with bypass_rls():
            try:
                org = Organization.objects.get(slug=options["slug"])
            except Organization.DoesNotExist:
                raise CommandError(f"No organization with slug '{options['slug']}'.")

            if options["unlist"]:
                org.public_contact = ""
            elif options["contact"] is not None:
                org.public_contact = options["contact"].strip()
            if options["serves"] is not None:
                org.serves = options["serves"].strip()
            org.save(update_fields=["public_contact", "serves"])

        listed = "listed" if org.public_contact else "NOT listed"
        self.stdout.write(self.style.SUCCESS(f"{org.name} is {listed} on /need-help/."))
