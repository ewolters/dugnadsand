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
                            help="Check who it would reach. Mints nothing.")

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

        if options["dry_run"]:
            # Every check above has run; the one thing that does not happen is
            # minting. The first version issued the link and THEN checked this
            # flag, so a rehearsal left a working credential in the database
            # and printed it to a terminal — the opposite of what the flag
            # promises. It cannot print a URL for the same reason: there is no
            # URL until a link exists.
            self.stdout.write(self.style.WARNING("Dry run — nothing minted, nothing sent."))
            self.stdout.write(f"  would email:  {user.email}")
            self.stdout.write(f"  for:          {member.display_name} "
                              f"({user.username}) in {member.organization.name}")
            self.stdout.write("  link:         not created — run without --dry-run")
            return

        token = issue_setup_link(member)
        link = f"{BASE_URL}/setup/{token}/"

        body = (
            f"Hello {member.display_name},\n\n"
            f"Your account for Dugnadsand is ready. Follow this link to choose a "
            f"password and set up a second factor:\n\n"
            f"    {link}\n\n"
            f"The link works once and expires in seven days. Your username is "
            f"{user.username}.\n\n"
            f"Dugnadsand writes down what happened and never what it was worth. "
            f"Hours given, material brought — kept in separate records, never added "
            f"together and never priced. None of it is a currency: nothing is bought, "
            f"sold or owed, and nothing you do or don't contribute changes what you "
            f"can ask for.\n\n"
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
