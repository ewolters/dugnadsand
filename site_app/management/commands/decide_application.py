"""Admit or decline an application.

A command, not a button, and the same posture as admit_organization: /policy/
tells every visitor there is no self-service signup, and an application that
admitted itself once its boxes went green would make that false while looking
like diligence.

Admitting refuses while anything required is unverified, expired, unscreened
or unagreed. Declining is always permitted -- a refusal needs no paperwork to
be complete.
"""

from datetime import date

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from site_app.models import Application
from site_app.services_applications import (AdmissionProblem, NotReady,
                                            admit_to_network, decline,
                                            record_screening, tell_decision,
                                            verify_credential)


class Command(BaseCommand):
    help = "Admit or decline an application, or record a check against it."

    def add_arguments(self, parser):
        parser.add_argument("application", help="Application id")
        parser.add_argument("--by", required=True, help="Your username")
        parser.add_argument("--admit", action="store_true")
        parser.add_argument("--decline", action="store_true")
        parser.add_argument("--verify", help="Credential kind to mark verified")
        parser.add_argument("--expires", help="YYYY-MM-DD, sets the expiry too")
        parser.add_argument("--screened", help="Registry that was searched")
        parser.add_argument("--searched-name", default="")
        parser.add_argument("--found", action="store_true",
                            help="Something came back that needs a person")
        parser.add_argument("--note", default="")
        parser.add_argument(
            "--into", help="Organization slug an individual is joining")
        parser.add_argument(
            "--username", help="Override the login name derived from the email")

    def handle(self, *args, **options):
        try:
            application = Application.objects.get(pk=options["application"])
        except (Application.DoesNotExist, ValueError, TypeError):
            raise CommandError("No application with that id.")
        try:
            user = User.objects.get(username=options["by"])
        except User.DoesNotExist:
            raise CommandError(f"No login called '{options['by']}'.")

        if options["verify"]:
            try:
                credential = application.credentials.get(kind=options["verify"])
            except Exception:
                raise CommandError(
                    "No such credential. This application has: "
                    + ", ".join(c.kind for c in application.credentials.all()))
            expires = (date.fromisoformat(options["expires"])
                       if options["expires"] else None)
            verify_credential(credential=credential, user=user,
                              verified_on=date.today(), expires_on=expires,
                              note=options["note"] or None)
            self.stdout.write(self.style.SUCCESS(f"Verified {credential.kind}."))

        if options["screened"]:
            record_screening(
                application=application, user=user, source=options["screened"],
                searched_name=options["searched_name"] or application.legal_name,
                searched_on=date.today(), clear=not options["found"],
                note=options["note"])
            self.stdout.write(self.style.SUCCESS(
                f"Recorded a search of {options['screened']}."))

        if options["decline"]:
            decline(application=application, user=user, note=options["note"])
            # After the write. The note stays internal: it is written for the
            # review, and forwarding it would publish somebody's shorthand.
            tell_decision(application)
            self.stdout.write(self.style.SUCCESS("Declined. The applicant has been told."))
            return

        if options["admit"]:
            into = None
            if options["into"]:
                from site_app.models import Organization
                try:
                    into = Organization.objects.get(slug=options["into"])
                except Organization.DoesNotExist:
                    raise CommandError(f"No organization with slug '{options['into']}'.")

            try:
                made = admit_to_network(
                    application=application, user=user, note=options["note"],
                    into=into, username=options["username"])
            except NotReady as refused:
                raise CommandError(
                    "Not admitted. Still needs: " + "; ".join(refused.blockers))
            except AdmissionProblem as problem:
                raise CommandError(str(problem))

            # The setup mail IS the acceptance when a login was created: it
            # carries the news and the thing to do next. Sending the decision
            # mail as well would deliver a second letter saying somebody will
            # be in touch to set up an account that is already set up.
            if not made["mailed"]:
                tell_decision(application)
            self.stdout.write(self.style.SUCCESS("Admitted."))

            if made["region"]:
                self.stdout.write(f"  chapter:  {made['region'].name} ({made['region'].slug})")
                self.stdout.write(
                    "  No login was created: there is no chapter screen to sign "
                    "into yet.\n  Give somebody a role with:\n"
                    f"    manage.py add_region_role {made['region'].slug} <username> --role lead")
                return

            self.stdout.write(f"  organization:  {made['organization'].name} "
                              f"({made['organization'].slug})")
            self.stdout.write(f"  first member:  {made['member'].display_name} "
                              f"({made['member'].user.username})")
            if made["mailed"]:
                self.stdout.write(self.style.SUCCESS(
                    "  setup link:    sent, single use, expires in 7 days"))
            else:
                self.stdout.write(self.style.WARNING(
                    "  setup link:    NOT SENT — the address is suppressed. "
                    "Resend with:\n"
                    f"    manage.py send_setup_link {made['member'].user.username}"))
            return

        for reason in application.blockers:
            self.stdout.write(self.style.WARNING(f"needs: {reason}"))
        if application.ready:
            self.stdout.write(self.style.SUCCESS("ready to decide"))
