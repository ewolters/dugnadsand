"""Add a member to an admitted organization, with a login.

Prints a one-time password rather than emailing one. Whoever runs this is
already talking to the new member — handing the credential over in that
conversation is simpler than putting it in an inbox, and leaks less.
"""

import secrets

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from site_app.models import Member, Organization
from site_app.tenancy import bypass_rls, tenant_context


class Command(BaseCommand):
    help = "Create a login and a membership in an admitted organization."

    def add_arguments(self, parser):
        parser.add_argument("org", help="Organization slug")
        parser.add_argument("username")
        parser.add_argument("display_name", help='How they appear to others, e.g. "Ada"')
        parser.add_argument("--email", default="")

    def handle(self, *args, **options):
        with bypass_rls():
            org = Organization.objects.filter(slug=options["org"]).first()
        if org is None:
            raise CommandError(
                f"No organization '{options['org']}'. Admit it first with "
                f"manage.py admit_organization.")

        username = options["username"].strip()
        if User.objects.filter(username=username).exists():
            raise CommandError(f"A user named '{username}' already exists.")

        password = secrets.token_urlsafe(12)

        with transaction.atomic():
            user = User.objects.create_user(
                username=username, email=options["email"], password=password)
            with tenant_context(org):
                Member.objects.create(
                    organization=org, user=user,
                    display_name=options["display_name"].strip())

        self.stdout.write(self.style.SUCCESS(
            f"Added {options['display_name']} to {org.name}."))
        self.stdout.write(f"  username: {username}")
        self.stdout.write(f"  password: {password}")
        self.stdout.write(self.style.WARNING(
            "  Shown once. Hand it over in person and have them change it."))
