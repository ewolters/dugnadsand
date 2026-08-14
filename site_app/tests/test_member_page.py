"""A name is a door.

Until this existed, a name in the feed linked to the posting it appeared on --
which is where you already were. There was no way to go from "Hannah said
something useful" to "who is Hannah", on a board whose entire purpose is that
people find each other.

Two things have to hold, and they pull in opposite directions:

  IT IS REACHABLE. A member of any organization in the chapter can open it.
  That is the whole point: the chapter is what people share, so a page that
  only worked inside one organization would rebuild the wall this system
  spent a migration tearing down.

  IT CARRIES NO NUMBER. Not hours, not a count of postings, not "here since"
  set beside somebody else's. A page that can be read next to another one and
  compared is a scoreboard however quietly it is set, and a scoreboard
  reintroduces by social pressure exactly what no-gating removes from the
  code.
"""

import re

from django.contrib.auth.models import User
from django.test import TestCase

from site_app.models import Member, Organization, Posting, Region
from site_app.tenancy import set_tenant, tenant_context

from .helpers import SignedIn


class Fixture(SignedIn, TestCase):
    def setUp(self):
        self.upstate = Region.objects.create(slug="up", name="Upstate")
        self.elsewhere = Region.objects.create(slug="mid", name="Midlands")

        self.ouat = Organization.objects.create(
            slug="ouat", name="Once Upon A Table", region=self.upstate,
            kind=Organization.AID_GROUP)
        self.svend = Organization.objects.create(
            slug="svend", name="SVEND", region=self.upstate,
            kind=Organization.BUSINESS)
        self.far = Organization.objects.create(
            slug="far", name="Far Co", region=self.elsewhere)

        self.hannah = self.member_for(self.ouat, "hannah", "Hannah")
        self.eric = self.member_for(self.svend, "eric", "Eric")
        self.stranger = self.member_for(self.far, "sam", "Sam")

        with tenant_context(self.ouat):
            self.posting = Posting.objects.create(
                organization=self.ouat, member=self.hannah,
                kind=Posting.OFFER, description="A trailer, most Saturdays.")
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

    def url(self, member=None):
        return f"/member/{(member or self.hannah).id}/"


class WhoCanOpenIt(Fixture):
    def test_somebody_in_the_same_organization_can(self):
        self.sign_in(self.hannah.user)
        self.assertEqual(self.client.get(self.url()).status_code, 200)

    def test_SOMEBODY_ELSE_IN_THE_CHAPTER_CAN(self):
        """The one that matters. Eric is at SVEND and Hannah is at Once Upon
        A Table; they share a chapter, and the chapter is what people share.
        A profile that stopped at the organization boundary would rebuild the
        wall a whole migration went into tearing down."""
        self.sign_in(self.eric.user)
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hannah")

    def test_somebody_in_another_chapter_cannot(self):
        """No permission code does this -- Member is tenant-scoped and RLS
        admits this organization or its chapter, so from outside it the row
        does not exist."""
        self.sign_in(self.stranger.user)
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_a_signed_out_visitor_cannot(self):
        self.assertNotEqual(self.client.get(self.url()).status_code, 200)


class WhatItShows(Fixture):
    def test_it_names_the_organization(self):
        self.sign_in(self.eric.user)
        self.assertContains(self.client.get(self.url()), "Once Upon A Table")

    def test_it_lists_what_they_have_up(self):
        self.sign_in(self.eric.user)
        self.assertContains(self.client.get(self.url()),
                            "A trailer, most Saturdays.")

    def test_a_closed_posting_drops_off(self):
        """A profile that accumulated everything somebody ever posted would
        become a record OF them rather than a way to reach them."""
        with tenant_context(self.ouat):
            Posting.objects.filter(pk=self.posting.pk).update(open=False)
        self.sign_in(self.eric.user)
        self.assertNotContains(self.client.get(self.url()),
                               "A trailer, most Saturdays.")

    def test_it_offers_thanks_for_somebody_else(self):
        self.sign_in(self.eric.user)
        self.assertContains(self.client.get(self.url()), "Say thanks")

    def test_it_does_not_offer_thanks_to_yourself(self):
        self.sign_in(self.hannah.user)
        body = self.client.get(self.url()).content.decode()
        self.assertNotIn("Say thanks", body)
        self.assertIn("Change your mark", body)


class ItCarriesNoNumber(Fixture):
    """The absence, asserted rather than trusted."""

    def test_no_digit_appears_in_the_prose(self):
        """Deliberately blunt. Any number on a page about a person can be
        read beside the same number on a page about somebody else, and at
        that moment the page is a scoreboard. Timestamps live inside the
        posting cards and are stripped with the markup."""
        import html as html_mod

        self.sign_in(self.eric.user)
        body = self.client.get(self.url()).content.decode()
        # The page above the postings list: the part that is about the person.
        head = body.split("<h2>")[0]
        head = re.sub(r"<(script|style)\b.*?</\1>", " ", head, flags=re.S)
        head = re.sub(r"<[^>]+>", " ", head)
        prose = html_mod.unescape(re.sub(r"\s+", " ", head))
        self.assertEqual(re.findall(r"\d", prose), [])

    def test_the_view_totals_nothing(self):
        import inspect

        from site_app import views

        source = inspect.getsource(views.member_page)
        for forbidden in ("aggregate(", "Sum(", "Count(", ".count()"):
            self.assertNotIn(forbidden, source)


class ANameIsADoor(Fixture):
    def test_the_feed_links_a_name_to_the_person(self):
        self.sign_in(self.eric.user)
        body = self.client.get("/board/").content.decode()
        self.assertIn(f'href="/member/{self.hannah.id}/"', body)

    def test_the_posting_page_does_too(self):
        self.sign_in(self.eric.user)
        body = self.client.get(f"/board/{self.posting.id}/").content.decode()
        self.assertIn(f'href="/member/{self.hannah.id}/"', body)
