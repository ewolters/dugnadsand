"""Email somebody a single-use link to set up their own account.

Preferred over add_member's printed password: nothing that works travels by
email, the link expires, and it can only be followed once. The member chooses a
password nobody else has ever seen, then enrolls a second factor.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from kjerne_platform import email as platform_email

from site_app.models import Member
from site_app.services_setup import issue_setup_link
from site_app.tenancy import bypass_rls

SITE = "dugnadsand"
BASE_URL = "https://dugnadsand.org"


class Command(BaseCommand):
    help = "Send a member a single-use link to choose their password."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--dry-run", action="store_true",
                            help="Print the link instead of sending it.")

    def handle(self, *args, **options):
        user = User.objects.filter(username=options["username"]).first()
        if user is None:
            raise CommandError(f"No user '{options['username']}'.")
        if not (user.email or "").strip():
            raise CommandError(
                f"{user.username} has no email address. Add one first — the "
                f"second factor is keyed to it.")

        with bypass_rls():
            member = Member.objects.filter(user=user).select_related("organization").first()
        if member is None:
            raise CommandError(f"{user.username} is not a member of any organization.")

        token = issue_setup_link(member)
        link = f"{BASE_URL}/setup/{token}/"

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — nothing sent."))
            self.stdout.write(f"  {link}")
            return

        body = (
            f"Hello {member.display_name},\n\n"
            f"Your account for Dugnadsand is ready. Follow this link to choose a "
            f"password and set up a second factor:\n\n"
            f"    {link}\n\n"
            f"The link works once and expires in seven days. Your username is "
            f"{user.username}.\n\n"
            f"Dugnadsand keeps one record: hours given. It is not a currency — nothing "
            f"is bought, sold or owed, and nothing you do or don't contribute changes "
            f"what you can ask for.\n\n"
            f"{BASE_URL}\n"
        )

        queued = platform_email.send(
            to=user.email,
            subject="Your Dugnadsand account",
            body=body,
            site=SITE,
            from_name="Dugnadsand",
        )
        if queued is None:
            raise CommandError(
                f"{user.email} is on the suppression list; nothing was sent.")

        self.stdout.write(self.style.SUCCESS(f"Setup link sent to {user.email}."))
        self.stdout.write("  Single use, expires in 7 days.")
