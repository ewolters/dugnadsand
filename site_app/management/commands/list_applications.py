"""What is waiting, and what each one still owes.

Prints the blockers rather than a count, because a count tells somebody there
is work and not what the work is.
"""

from django.core.management.base import BaseCommand

from site_app.models import Application


class Command(BaseCommand):
    help = "List applications and what each still needs."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true",
                            help="Include applications already decided")

    def handle(self, *args, **options):
        rows = Application.objects.all()
        if not options["all"]:
            rows = rows.filter(admitted__isnull=True)

        if not rows:
            self.stdout.write("Nothing waiting.")
            return

        for a in rows.select_related("region"):
            self.stdout.write(
                f"\n{a.id}\n  {a.get_kind_display()}: {a.legal_name}"
                f"{f' -> {a.region.name}' if a.region else ''}"
                f"\n  {a.contact_name} <{a.email}>  submitted {a.submitted_at:%Y-%m-%d}")
            if a.decided:
                self.stdout.write(
                    f"  DECIDED: {'admitted' if a.admitted else 'declined'}")
                continue
            for reason in a.blockers:
                self.stdout.write(self.style.WARNING(f"  needs: {reason}"))
            if a.ready:
                self.stdout.write(self.style.SUCCESS("  ready to decide"))
