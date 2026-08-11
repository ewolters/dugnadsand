"""Open a chapter.

A command rather than a form, for the same reason admit_organization is one:
a chapter is a group of people who have agreed to run something in a place,
and it exists once that has actually happened. Applications to START a chapter
are a separate thing and arrive through the network's own ingress; this is the
step somebody takes after that conversation has concluded.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from site_app.models import Region


class Command(BaseCommand):
    help = "Open a regional chapter."

    def add_arguments(self, parser):
        parser.add_argument("name", help='e.g. "Upstate South Carolina"')
        parser.add_argument("--slug", help="Derived from the name if omitted")
        parser.add_argument("--covers", default="",
                            help="Where it covers, in words")

    def handle(self, *args, **options):
        name = options["name"].strip()
        slug = slugify(options["slug"] or name)
        if not slug:
            raise CommandError("Could not derive a slug; pass --slug explicitly.")
        if Region.objects.filter(slug=slug).exists():
            raise CommandError(f"A chapter with slug '{slug}' already exists.")

        region = Region.objects.create(
            slug=slug, name=name, covers=options["covers"].strip())

        self.stdout.write(self.style.SUCCESS(f"Opened {region.name} ({region.slug})."))
        self.stdout.write(
            "Give somebody a role with:\n"
            f'  manage.py add_region_role {region.slug} <username> --role lead\n'
            "Admit an organization into it with:\n"
            f'  manage.py admit_organization "<name>" --region {region.slug}')
