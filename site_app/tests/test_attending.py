"""Saying you will be there.

A work day has had a date, a place and a muster point since it existed, and no
way for anybody to say they were coming — so "who is turning up on Saturday"
lived in somebody's texts, and whoever was deciding how many trailers to bring
was the one who had to go and ask.

The shape is Interest's, because Interest already solved this once for
postings. What is different is that a day has a DATE, and that makes the
social weight heavier: "I'll be there Saturday" and then not going is visible
in a way "I might be able to help" never is. So the guarantees matter more
here, not less.

  NAMED, NEVER COUNTED. The card says who. It does not say how many. A number
  beside a day is a turnout figure, and a turnout figure invites comparing
  this Saturday to the last one and this person to that one.

  NOTHING RECORDS WHETHER SOMEBODY CAME. No attended flag, no no-show, no
  chase. Withdrawing is a hard delete leaving no trace.

  NOTHING TO FALL SHORT OF. No capacity, no expected number, no target. See
  test_events.py — a list of who said they would come is a guest list; the
  same list measured against a number is a quota.
"""

import re

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from site_app.models import Attending, Member, Organization, Region, WorkDay
from site_app.services_events import DayCalledOff, coming, not_coming
from site_app.tenancy import set_tenant, tenant_context

from .helpers import SignedIn


class DayBase(SignedIn, TestCase):
    def setUp(self):
        self.region = Region.objects.create(slug="up", name="Upstate")
        self.ouat = Organization.objects.create(
            slug="ouat", name="Once Upon A Table", region=self.region,
            kind=Organization.AID_GROUP)
        self.svend = Organization.objects.create(
            slug="svend", name="SVEND", region=self.region,
            kind=Organization.BUSINESS)

        self.hannah = self.member_for(self.ouat, "hannah", "Hannah")
        self.eric = self.member_for(self.svend, "eric", "Eric")

        with tenant_context(self.ouat):
            self.day = WorkDay.objects.create(
                organization=self.ouat, called_by=self.hannah,
                name="Clear the lot on Pendleton",
                description="Bring gloves.",
                place="The lot behind the church",
                starts_at=timezone.now() + timezone.timedelta(days=3))
        set_tenant(None)

    def tearDown(self):
        set_tenant(None)

    def member_for(self, organization, username, display):
        user = User.objects.create_user(username, password="dugnad-test-pw")
        set_tenant(organization.id, organization.region_id)
        member = Member.objects.create(organization=organization, user=user,
                                       display_name=display)
        set_tenant(None)
        return member


class SayingYouWillBeThere(DayBase):
    def test_a_member_can_say_they_are_coming(self):
        with tenant_context(self.ouat):
            coming(day=self.day, member=self.hannah)
            self.assertEqual(Attending.objects.count(), 1)

    def test_SOMEBODY_FROM_ANOTHER_ORGANIZATION_IN_THE_CHAPTER_CAN(self):
        """The one that matters. A work day is the most physical thing this
        system has, and a day only its own organization could turn up to
        would be the chapter boundary undone at the one place it is most
        obviously wrong."""
        with tenant_context(self.svend):
            coming(day=self.day, member=self.eric)

        with tenant_context(self.ouat):
            self.assertEqual(
                [a.member.display_name for a in self.day.attending.all()],
                ["Eric"])

    def test_saying_it_twice_updates_rather_than_duplicating(self):
        with tenant_context(self.ouat):
            coming(day=self.day, member=self.hannah, bringing="the flatbed")
            coming(day=self.day, member=self.hannah, bringing="the flatbed and a saw")

            self.assertEqual(Attending.objects.count(), 1)
            self.assertEqual(Attending.objects.get().bringing,
                             "the flatbed and a saw")

    def test_what_somebody_is_bringing_is_free_text_and_optional(self):
        with tenant_context(self.ouat):
            coming(day=self.day, member=self.hannah)
            self.assertEqual(Attending.objects.get().bringing, "")

    def test_a_called_off_day_refuses(self):
        """Somebody arriving at a called-off day because the button still
        worked is the failure this exists to prevent."""
        from site_app.services_events import cancel

        with tenant_context(self.ouat):
            cancel(self.day, because="The county said no.")
            with self.assertRaises(DayCalledOff):
                coming(day=WorkDay.objects.get(pk=self.day.pk),
                       member=self.hannah)
            self.assertEqual(Attending.objects.count(), 0)


class ChangingYourMindCostsNothing(DayBase):
    def test_withdrawing_is_a_hard_delete(self):
        with tenant_context(self.ouat):
            coming(day=self.day, member=self.hannah)
            not_coming(day=self.day, member=self.hannah)
            self.assertEqual(Attending.objects.count(), 0)

    def test_withdrawing_leaves_no_trace_of_having_said_yes(self):
        """A cancelled flag would be a record of somebody changing their
        mind, and anything stored can be counted."""
        from django.db import connection

        with tenant_context(self.ouat):
            coming(day=self.day, member=self.hannah)
            not_coming(day=self.day, member=self.hannah)

        with connection.cursor() as cursor:
            cursor.execute("SET app.bypass_rls = 'on'")
            cursor.execute("SELECT count(*) FROM site_app_attending")
            self.assertEqual(cursor.fetchone()[0], 0)

    def test_withdrawing_when_you_never_said_yes_is_quiet(self):
        with tenant_context(self.ouat):
            not_coming(day=self.day, member=self.hannah)


class NamedNeverCounted(DayBase):
    def test_the_page_lists_names_and_prints_no_number(self):
        with tenant_context(self.ouat):
            coming(day=self.day, member=self.hannah, bringing="the flatbed")
        with tenant_context(self.svend):
            coming(day=self.day, member=self.eric)

        self.sign_in(self.hannah.user)
        body = self.client.get(f"/days/{self.day.id}/").content.decode()

        self.assertIn("Hannah", body)
        self.assertIn("Eric", body)
        self.assertIn("the flatbed", body)

        # Two people are coming, and "2" must not appear as a count anywhere
        # near them. Scoped to the section rather than the page, because a
        # date elsewhere legitimately carries digits.
        section = body[body.index("Who is coming"):body.index("Permissions")]
        section = re.sub(r"<[^>]+>", " ", section)
        self.assertEqual(re.findall(r"\d", section), [])

    def test_no_template_counts_the_attendance(self):
        """The absence, asserted against the templates rather than trusted.
        A |length filter on this relation is the whole failure in one word."""
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[2]
        offenders = []
        for path in (root / "site_app" / "templates").rglob("*.html"):
            text = path.read_text()
            if re.search(r"attending[^%}]*\|\s*length|attending\.count", text):
                offenders.append(str(path.relative_to(root)))
        self.assertEqual(offenders, [])

    def test_no_view_counts_it_either(self):
        import inspect

        from site_app import views

        source = inspect.getsource(views)
        for forbidden in ("attending.count()", "Count(\"attending\")",
                          "Count('attending')"):
            self.assertNotIn(forbidden, source)


class ThroughTheDoor(DayBase):
    def test_the_button_records_it(self):
        self.sign_in(self.eric.user)
        self.client.post(f"/days/{self.day.id}/coming/",
                         {"bringing": "a chainsaw"})

        with tenant_context(self.ouat):
            entry = Attending.objects.get()
            self.assertEqual(entry.member, self.eric)
            self.assertEqual(entry.bringing, "a chainsaw")

    def test_the_withdraw_button_removes_it(self):
        self.sign_in(self.eric.user)
        self.client.post(f"/days/{self.day.id}/coming/", {})
        self.client.post(f"/days/{self.day.id}/coming/", {"withdraw": "1"})

        with tenant_context(self.ouat):
            self.assertEqual(Attending.objects.count(), 0)

    def test_a_signed_out_visitor_cannot(self):
        self.client.post(f"/days/{self.day.id}/coming/", {})
        with tenant_context(self.ouat):
            self.assertEqual(Attending.objects.count(), 0)

    def test_the_list_page_offers_it_too(self):
        """A day somebody has to open before they can say they are coming is
        a day most people never say they are coming to."""
        self.sign_in(self.eric.user)
        body = self.client.get("/days/").content.decode()
        self.assertIn(f'action="/days/{self.day.id}/coming/"', body)
