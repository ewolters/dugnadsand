"""Add a member to an admitted organization, with a login.

Prints a one-time password rather than emailing one. Whoever runs this is
already talking to the new member — handing the credential over in that
conversation is simpler than putting it in an inbox, and leaks less.

The first member of a new organization needs --organizer, otherwise nobody
inside it can add anyone else and every addition needs shell access.
"""

from django.core.management.base import BaseCommand, CommandError

from site_app.models import Organization
from site_app.services_members import MemberExists, create_member
from site_app.tenancy import bypass_rls


class Command(BaseCommand):
    help = "Create a login and a membership in an admitted organization."

    def add_arguments(self, parser):
        parser.add_argument("org", help="Organization slug")
        parser.add_argument("username")
        parser.add_argument("display_name", help='How they appear to others, e.g. "Ada"')
        parser.add_argument("email", help="Required: the second factor is keyed by it")
        parser.add_argument(
            "--organizer", action="store_true",
            help="May add other members. The first member of an organization needs this.")

    def handle(self, *args, **options):
        with bypass_rls():
            org = Organization.objects.filter(slug=options["org"]).first()
        if org is None:
            raise CommandError(
                f"No organization '{options['org']}'. Admit it first with "
                f"manage.py admit_organization.")

        try:
            member, password = create_member(
                organization=org,
                username=options["username"],
                display_name=options["display_name"],
                email=options["email"],
                is_organizer=options["organizer"],
            )
        except (MemberExists, ValueError) as exc:
            raise CommandError(str(exc))

        role = " (organizer)" if member.is_organizer else ""
        self.stdout.write(self.style.SUCCESS(
            f"Added {member.display_name} to {org.name}{role}."))
        self.stdout.write(f"  username: {options['username'].strip()}")
        self.stdout.write(f"  password: {password}")
        self.stdout.write(self.style.WARNING(
            "  Shown once. Hand it over in person; they must change it at first sign-in."))
