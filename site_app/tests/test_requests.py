"""Somebody asks for help, and one aid group answers.

This is the seam the whole policy turns on. Everything upstream of it is
organizations logging what they moved between each other; everything
downstream of it is a group and a person, and none of that is recorded here.

Three properties are worth more than the rest:

  BLIND. The need and a coarse area are shown. The name and the way to reach
  them are withheld from everybody — including chapter officers, including
  other aid groups — until one group takes it up.

  AID GROUPS ONLY. A business in the network cannot see a request at all. The
  refusal is on the stored kind, set by an officer at admission, and not on
  anything the requester or the business can influence. It is access control,
  not a certification -- the network does not vouch for its members.

  NO OUTCOME. Nothing records whether anybody was helped. A field for it
  would be this system reaching into the last mile, which the policy says it
  does not do.
"""

import time

from django.core import signing
from django.test import TestCase

from site_app.models import Member, Organization, Region, Request
from site_app.services_requests import (AlreadyTaken, NotAnAidGroup,
                                        close_request, forget_stale,
                                        release_request, submit_request,
                                        take_request, visible_to)
from site_app.tenancy import set_tenant

from .helpers import SignedIn


def stamped(**fields):
    """A POST body carrying a stamp minted five seconds ago.

    The form refuses anything faster than two seconds, so a test that minted
    one at post time would be refused for looking like a script — which is
    the point of the stamp, and not what any of these tests are about.
    """
    from site_app.forms import RequestForm

    signer = signing.Signer(salt=RequestForm.STAMP_SALT)
    return {"t": signer.sign(str(int(time.time()) - 5)), "website": "",
            **fields}


class Intake(TestCase):
    """The public form. No account, no session, no tenant."""

    def setUp(self):
        self.upstate = Region.objects.create(
            slug="upstate", name="Upstate SC and WNC")

    def tearDown(self):
        set_tenant(None)

    def test_anybody_can_ask_without_joining_anything(self):
        response = self.client.post("/need-help/", stamped(
            need="A ride to dialysis on Thursdays.",
            reach_them="864 555 0102", asked_by="Marta",
            area="Travelers Rest", region=str(self.upstate.id)))

        self.assertEqual(response.status_code, 200)
        request = Request.objects.get()
        self.assertEqual(request.need, "A ride to dialysis on Thursdays.")
        self.assertEqual(request.region, self.upstate)

    def test_a_blind_post_is_refused(self):
        """No stamp means the page was never loaded. CSRF protects nothing
        here — there is no session to ride — but the incidental property, that
        a scripted POST is refused, is the one worth keeping."""
        self.client.post("/need-help/", {
            "need": "x", "reach_them": "y", "t": "", "website": ""})
        self.assertEqual(Request.objects.count(), 0)

    def test_the_name_and_the_contact_are_encrypted_at_rest(self):
        """Whoever ends up holding a copy of this database — a backup, a
        replica, a subpoena served on the host — reads the need and not the
        person."""
        from django.db import connection

        submit_request(need="A ride.", reach_them="864 555 0102",
                       asked_by="Marta", region=self.upstate)

        with connection.cursor() as cursor:
            cursor.execute("SET app.bypass_rls = 'on'")
            cursor.execute("SELECT asked_by, reach_them, need "
                           "FROM site_app_request")
            asked_by, reach_them, need = cursor.fetchone()

        self.assertNotIn("Marta", asked_by)
        self.assertNotIn("555", reach_them)
        # The need is NOT encrypted, and should not be: it is the part that
        # is shown. Encrypting it would cost the search that finds the group
        # who can help and buy nothing.
        self.assertIn("ride", need)

    def test_it_says_what_is_needed_before_it_asks_who_is_asking(self):
        """Field order is not decoration on a form somebody fills in while
        their week is falling apart. The first box is the one they came to
        write in."""
        body = self.client.get("/need-help/").content.decode()
        self.assertLess(body.index('name="need"'), body.index('name="asked_by"'))


class WhoCanSeeIt(SignedIn, TestCase):
    """The blind half. This is the test to read first."""

    def setUp(self):
        self.upstate = Region.objects.create(slug="upstate", name="Upstate")
        self.midlands = Region.objects.create(slug="mid", name="Midlands")

        self.group = Organization.objects.create(
            slug="ouat", name="Once Upon A Table", region=self.upstate,
            kind=Organization.AID_GROUP)
        self.shop = Organization.objects.create(
            slug="svend", name="SVEND", region=self.upstate,
            kind=Organization.BUSINESS)
        self.far_group = Organization.objects.create(
            slug="far", name="Far Group", region=self.midlands,
            kind=Organization.AID_GROUP)

        self.hannah = self.member_for(self.group, "hannah")
        self.eric = self.member_for(self.shop, "eric")
        self.stranger = self.member_for(self.far_group, "stranger")

        self.request = submit_request(
            need="A ride to dialysis.", reach_them="864 555 0102",
            asked_by="Marta", area="Travelers Rest", region=self.upstate)
        set_tenant(None)

    def tearDown(self):
        set_tenant(None)

    def member_for(self, organization, username):
        from django.contrib.auth.models import User

        user = User.objects.create_user(username, password="dugnad-test-pw")
        set_tenant(organization.id, organization.region_id)
        member = Member.objects.create(
            organization=organization, user=user, display_name=username)
        set_tenant(None)
        return member

    def test_an_aid_group_in_that_chapter_sees_it(self):
        self.assertIn(self.request, visible_to(self.hannah))

    def test_a_BUSINESS_in_the_same_chapter_sees_nothing(self):
        """The one that would sink this if it broke. A business donating
        pallets has no business reading who on which street is struggling,
        and there is no setting that turns this on."""
        self.assertEqual(list(visible_to(self.eric)), [])

    def test_an_aid_group_in_ANOTHER_chapter_sees_nothing(self):
        self.assertEqual(list(visible_to(self.stranger)), [])

    def test_the_feed_shows_the_need_and_never_the_contact(self):
        self.sign_in(self.hannah.user)
        body = self.client.get("/board/").content.decode()

        self.assertIn("A ride to dialysis.", body)
        self.assertIn("Travelers Rest", body)
        self.assertNotIn("864 555 0102", body)
        self.assertNotIn("Marta", body)

    def test_a_business_feed_carries_no_request_at_all(self):
        self.sign_in(self.eric.user)
        body = self.client.get("/board/").content.decode()
        self.assertNotIn("A ride to dialysis.", body)

    def test_taking_it_up_discloses_the_contact_to_that_group_alone(self):
        take_request(request=self.request, member=self.hannah)

        self.sign_in(self.hannah.user)
        self.assertContains(self.client.get("/board/"), "864 555 0102")

        # And to nobody else, including another aid group in the chapter.
        other = Organization.objects.create(
            slug="other", name="Other", region=self.upstate,
            kind=Organization.AID_GROUP)
        onlooker = self.member_for(other, "onlooker")
        set_tenant(None)
        self.sign_in(onlooker.user)
        self.assertNotContains(self.client.get("/board/"), "864 555 0102")


class Taking(WhoCanSeeIt):
    def test_a_business_cannot_take_one_even_by_posting_the_id(self):
        """visible_to hides it; this is the half that would matter. A URL
        somebody was sent is not a permission."""
        with self.assertRaises(NotAnAidGroup):
            take_request(request=self.request, member=self.eric)
        self.assertIsNone(Request.objects.get(pk=self.request.pk).taken_by)

    def test_a_group_from_another_chapter_cannot(self):
        with self.assertRaises(NotAnAidGroup):
            take_request(request=self.request, member=self.stranger)

    def test_two_groups_cannot_both_win(self):
        """Not politeness. Two groups turning up at one door is worse than
        one, for the person who asked."""
        other = Organization.objects.create(
            slug="other", name="Other", region=self.upstate,
            kind=Organization.AID_GROUP)
        second = self.member_for(other, "second")
        set_tenant(None)

        take_request(request=self.request, member=self.hannah)
        with self.assertRaises(AlreadyTaken):
            take_request(request=self.request, member=second)

        self.assertEqual(Request.objects.get(pk=self.request.pk).taken_by,
                         self.group)

    def test_putting_it_back_leaves_no_mark(self):
        """A group that finds it cannot help has to be able to say so without
        that becoming a record against them or against the person."""
        take_request(request=self.request, member=self.hannah)
        release_request(request=self.request, member=self.hannah)

        fresh = Request.objects.get(pk=self.request.pk)
        self.assertIsNone(fresh.taken_by)
        self.assertIsNone(fresh.taken_at)

    def test_only_the_holding_group_can_put_it_back(self):
        take_request(request=self.request, member=self.hannah)
        with self.assertRaises(NotAnAidGroup):
            release_request(request=self.request, member=self.stranger)


class NoOutcomeIsRecorded(TestCase):
    """The absence that the policy promises, asserted as a property.

    Closing a request takes it off the list and records nothing about what
    happened. If a field for that ever appears, this fails, and somebody has
    to argue for it in the open rather than adding it quietly.
    """

    def test_the_model_carries_no_field_for_what_happened(self):
        names = {f.name for f in Request._meta.get_fields()}
        for forbidden in ("outcome", "result", "resolved", "helped",
                          "satisfied", "rating", "value", "amount",
                          "fulfilled", "delivered", "notes"):
            self.assertNotIn(forbidden, names)

    def test_closing_records_only_that_it_closed(self):
        region = Region.objects.create(slug="up", name="Upstate")
        group = Organization.objects.create(
            slug="g", name="G", region=region, kind=Organization.AID_GROUP)

        from django.contrib.auth.models import User

        user = User.objects.create_user("h", password="dugnad-test-pw")
        set_tenant(group.id, region.id)
        member = Member.objects.create(organization=group, user=user,
                                       display_name="H")
        set_tenant(None)

        request = submit_request(need="A ride.", reach_them="x", region=region)
        take_request(request=request, member=member)
        close_request(request=request, member=member)

        fresh = Request.objects.get(pk=request.pk)
        self.assertIsNotNone(fresh.closed_at)
        # It is off the list, and that is the entire record of the ending.
        self.assertEqual(list(visible_to(member)), [])


class TheContactIsNotKept(TestCase):
    """You cannot leak what you deleted.

    The name and the way to reach somebody are the most sensitive things this
    system holds: they belong to a person who was having a bad month and who
    never joined anything. Once a group has made contact, nothing reads them
    again — so keeping them would be keeping a list of who in the county
    needed help, indexed by phone number, against no future use at all.

    The ROW survives both paths. It is what says a chapter was asked and how
    long anybody took to answer, and a chapter that quietly never answers
    should not be able to erase that by doing nothing.
    """

    def setUp(self):
        from django.contrib.auth.models import User

        self.region = Region.objects.create(slug="up", name="Upstate")
        self.group = Organization.objects.create(
            slug="g", name="G", region=self.region, kind=Organization.AID_GROUP)
        user = User.objects.create_user("h", password="dugnad-test-pw")
        set_tenant(self.group.id, self.region.id)
        self.member = Member.objects.create(
            organization=self.group, user=user, display_name="H")
        set_tenant(None)

    def tearDown(self):
        set_tenant(None)

    def a_request(self):
        return submit_request(need="A ride to dialysis.", asked_by="Marta",
                              reach_them="864 555 0102", region=self.region)

    def test_closing_erases_the_name_and_the_contact(self):
        request = self.a_request()
        take_request(request=request, member=self.member)
        close_request(request=request, member=self.member)

        fresh = Request.objects.get(pk=request.pk)
        self.assertEqual(fresh.asked_by, "")
        self.assertEqual(fresh.reach_them, "")

    def test_but_the_row_and_the_need_survive(self):
        request = self.a_request()
        take_request(request=request, member=self.member)
        close_request(request=request, member=self.member)

        fresh = Request.objects.get(pk=request.pk)
        self.assertEqual(fresh.need, "A ride to dialysis.")
        self.assertEqual(fresh.taken_by, self.group)
        self.assertIsNotNone(fresh.closed_at)

    def test_a_request_nobody_closed_is_forgotten_anyway(self):
        """The backstop. A group that goes quiet leaves a request open for
        ever, and for ever is the wrong retention period for the phone
        number of somebody in trouble."""
        from datetime import timedelta

        request = self.a_request()
        Request.objects.filter(pk=request.pk).update(
            created_at=request.created_at - timedelta(days=91))

        self.assertEqual(forget_stale(older_than_days=90), 1)
        fresh = Request.objects.get(pk=request.pk)
        self.assertEqual(fresh.reach_them, "")
        self.assertEqual(fresh.need, "A ride to dialysis.")

    def test_a_recent_one_is_left_alone(self):
        self.a_request()
        self.assertEqual(forget_stale(older_than_days=90), 0)
        self.assertEqual(Request.objects.get().reach_them, "864 555 0102")

    def test_it_does_not_keep_re_closing_what_it_already_forgot(self):
        """Idempotent, because it runs on a schedule. Re-stamping closed_at
        every night would make an old request look freshly handled."""
        from datetime import timedelta

        request = self.a_request()
        Request.objects.filter(pk=request.pk).update(
            created_at=request.created_at - timedelta(days=91))

        forget_stale(older_than_days=90)
        first = Request.objects.get(pk=request.pk).closed_at
        self.assertEqual(forget_stale(older_than_days=90), 0)
        self.assertEqual(Request.objects.get(pk=request.pk).closed_at, first)
