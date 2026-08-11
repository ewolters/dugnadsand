"""Give somebody a role in a chapter.

The role attaches to a LOGIN, not to a member. A member belongs to exactly one
organization, so hanging a chapter role off one would put the chapter's
leadership inside a member organization with that organization's records one
join away. The role grants no read of any organization's records and there is
no code path by which it could -- see Region's docstring.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from site_app.models import Region, RegionRole


class Command(BaseCommand):
    help = "Give a person a lead or administrator role in a chapter."

    def add_arguments(self, parser):
        parser.add_argument("region", help="Chapter slug")
        parser.add_argument("username")
        parser.add_argument("--role", default=RegionRole.ADMIN,
                            choices=[RegionRole.LEAD, RegionRole.ADMIN])
        parser.add_argument("--title", default="",
                            help='What they are called locally, e.g. "Convenor"')

    def handle(self, *args, **options):
        try:
            region = Region.objects.get(slug=options["region"])
        except Region.DoesNotExist:
            raise CommandError(f"No chapter with slug '{options['region']}'.")
        try:
            user = User.objects.get(username=options["username"])
        except User.DoesNotExist:
            raise CommandError(f"No login called '{options['username']}'.")

        role, created = RegionRole.objects.get_or_create(
            region=region, user=user, role=options["role"],
            defaults={"title": options["title"].strip()})
        if not created:
            raise CommandError(
                f"{user.username} is already {role.get_role_display()} of {region.name}.")

        self.stdout.write(self.style.SUCCESS(
            f"{user.username} is now {role.get_role_display()} of {region.name}."))
        self.stdout.write(
            "This grants no access to any organization's records. "
            "Membership of an organization is a separate thing.")
