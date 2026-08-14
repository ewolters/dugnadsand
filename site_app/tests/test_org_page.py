"""A group, and what it has up.

Members became objects you could open and organizations did not, so a name
like "Once Upon A Table" under every posting went nowhere. On a network whose
unit is the ORGANIZATION rather than the person, that was the wrong half to
have built first.

THE POINT OF THIS FILE is the chapter check. Everywhere else the boundary is
free: the model is TenantScoped, RLS admits this organization or any in its
chapter, and a stranger's row does not exist to the query. **Organization is
not tenant-scoped — it IS the tenant.** `Organization.objects.get(slug=...)`
reaches the entire table and no database rule stops it, so the boundary here
is a hand-written `if` in a view, which is precisely the kind that gets
deleted during a refactor by somebody who assumes RLS has it covered.

So it is asserted from the outside, by signing in and asking for the URL.
"""

import re

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from site_app.models import Member, Organization, Posting, Region, WorkDay
from site_app.tenancy import set_tenant, tenant_context

from .helpers import SignedIn


class OrgBase(SignedIn, TestCase):
    def setUp(self):
        self.upstate = Region.objects.create(slug="up", name="Upstate")
        self.midlands = Region.objects.create(slug="mid", name="Midlands")

        self.ouat = Organization.objects.create(
            slug="ouat", name="Once Upon A Table", region=self.upstate,
            kind=Organization.AID_GROUP, serves="Greenville and Pickens")
        self.svend = Organization.objects.create(
            slug="svend", name="SVEND", region=self.upstate,
            kind=Organization.BUSINESS)
        self.far = Organization.objects.create(
            slug="far", name="Far Co", region=self.midlands)
        # Admitted into no chapter at all.
        self.loner = Organization.objects.create(
            slug="loner", name="Loner Co", region=None)

        self.hannah = self.member_for(self.ouat, "hannah", "Hannah")
        self.eric = self.member_for(self.svend, "eric", "Eric")
        self.stranger = self.member_for(self.far, "sam", "Sam")
        self.solo = self.member_for(self.loner, "lee", "Lee")

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


class WhoCanOpenIt(OrgBase):
    """The hand-written boundary, asserted from outside the view."""

    def test_its_own_member_can(self):
        self.sign_in(self.hannah.user)
        self.assertEqual(self.client.get("/org/ouat/").status_code, 200)

    def test_ANOTHER_ORGANIZATION_IN_THE_CHAPTER_CAN(self):
        """The chapter is what people share. Eric is at SVEND and this is
        Once Upon A Table."""
        self.sign_in(self.eric.user)
        self.assertContains(self.client.get("/org/ouat/"), "Once Upon A Table")

    def test_AN_ORGANIZATION_IN_ANOTHER_CHAPTER_CANNOT(self):
        """No RLS policy does this. If the `if` in the view is ever removed
        by somebody assuming the database has it covered, this is what says
        so."""
        self.sign_in(self.stranger.user)
        self.assertEqual(self.client.get("/org/ouat/").status_code, 404)

    def test_two_chapterless_organizations_do_not_see_each_other(self):
        """The bug a null comparison would have written. Both have
        region=None, and `a.region_id == b.region_id` is True for two
        Nones — which would have put every chapterless organization in one
        undeclared chapter together."""
        other = Organization.objects.create(
            slug="loner2", name="Second Loner", region=None)
        outsider = self.member_for(other, "pat", "Pat")
        set_tenant(None)

        self.sign_in(outsider.user)
        self.assertEqual(self.client.get("/org/loner/").status_code, 404)

    def test_but_a_chapterless_organization_sees_itself(self):
        self.sign_in(self.solo.user)
        self.assertEqual(self.client.get("/org/loner/").status_code, 200)

    def test_a_closed_organization_is_gone(self):
        Organization.objects.filter(pk=self.ouat.pk).update(active=False)
        self.sign_in(self.eric.user)
        self.assertEqual(self.client.get("/org/ouat/").status_code, 404)

    def test_a_signed_out_visitor_cannot(self):
        self.assertNotEqual(self.client.get("/org/ouat/").status_code, 200)


class WhatItShows(OrgBase):
    def test_it_names_the_people(self):
        self.sign_in(self.eric.user)
        self.assertContains(self.client.get("/org/ouat/"), "Hannah")

    def test_it_lists_what_they_have_up(self):
        self.sign_in(self.eric.user)
        self.assertContains(self.client.get("/org/ouat/"),
                            "A trailer, most Saturdays.")

    def test_it_says_the_kind(self):
        """A fact with consequences: a mutual aid group can take up a request
        from somebody who asked for help and a business cannot."""
        self.sign_in(self.eric.user)
        self.assertContains(self.client.get("/org/ouat/"), "Mutual aid group")

    def test_it_says_admission_is_not_a_recommendation(self):
        """A group page is exactly where somebody infers that being listed
        means being vouched for."""
        self.sign_in(self.eric.user)
        self.assertContains(self.client.get("/org/ouat/"),
                            "not a recommendation")

    def test_it_shows_a_day_they_called(self):
        with tenant_context(self.ouat):
            WorkDay.objects.create(
                organization=self.ouat, called_by=self.hannah,
                name="Clear the lot", description="Bring gloves.",
                place="Behind the church",
                starts_at=timezone.now() + timezone.timedelta(days=3))

        self.sign_in(self.eric.user)
        self.assertContains(self.client.get("/org/ouat/"), "Clear the lot")

    def test_it_shows_nothing_from_another_organization(self):
        with tenant_context(self.svend):
            Posting.objects.create(
                organization=self.svend, member=self.eric,
                kind=Posting.OFFER, description="SVEND has a projector.")

        self.sign_in(self.eric.user)
        body = self.client.get("/org/ouat/").content.decode()
        self.assertNotIn("SVEND has a projector.", body)

        # Scoped to the roster. "Eric" is legitimately in the chrome — the
        # account menu names whoever is signed in — and a bare assertion over
        # the whole page tests the header, not the page.
        roster = body[body.index("Who is here"):body.index("What they have up")]
        self.assertNotIn("Eric", roster)
        self.assertIn("Hannah", roster)


class ItCarriesNoNumber(OrgBase):
    """Same rule as a member page. Two of these side by side must not invite
    a comparison, and a count of members is the first thing that would."""

    def test_no_digit_appears_above_the_lists(self):
        import html as html_mod

        self.sign_in(self.eric.user)
        body = self.client.get("/org/ouat/").content.decode()
        head = body.split("<h2>")[0]
        head = re.sub(r"<(script|style)\b.*?</\1>", " ", head, flags=re.S)
        prose = html_mod.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", head)))
        self.assertEqual(re.findall(r"\d", prose), [])

    def test_no_template_counts_the_members(self):
        import pathlib

        page = (pathlib.Path(__file__).resolve().parents[1] / "templates"
                / "site_app" / "organization.html").read_text()
        self.assertNotIn("|length", page)
        self.assertNotIn(".count", page)

    def test_the_view_totals_nothing(self):
        import inspect

        from site_app import views

        source = inspect.getsource(views.organization_page)
        for forbidden in ("aggregate(", "Sum(", "Count(", ".count()"):
            self.assertNotIn(forbidden, source)


class ANameIsADoor(OrgBase):
    def test_the_feed_links_the_organization(self):
        self.sign_in(self.eric.user)
        self.assertContains(self.client.get("/board/"), 'href="/org/ouat/"')

    def test_the_member_page_links_it(self):
        self.sign_in(self.eric.user)
        self.assertContains(self.client.get(f"/member/{self.hannah.id}/"),
                            'href="/org/ouat/"')

    def test_the_posting_page_links_it(self):
        self.sign_in(self.eric.user)
        self.assertContains(self.client.get(f"/board/{self.posting.id}/"),
                            'href="/org/ouat/"')


class WhatIsOnTheirShelf(OrgBase):
    """The warehouse, surfaced where people actually look.

    Material lived at /warehouse/ and nothing in the social half of the site
    pointed at it, so a group's shelf was invisible to the chapter it was for.
    """

    def a_line(self, description="Reclaimed oak, mostly 2x8"):
        from decimal import Decimal

        from django.utils import timezone

        from site_app.models import StockLine, Warehouse

        with tenant_context(self.ouat):
            barn = Warehouse.objects.create(
                organization=self.ouat, holder=self.hannah,
                name="North barn", address="Gate code 4412")
            return StockLine.objects.create(
                organization=self.ouat, warehouse=barn,
                description=description, quantity=Decimal("200.00"),
                unit="board-feet", confirmed_at=timezone.now(),
                confirmed_by=self.hannah)

    def test_a_chapter_peer_sees_what_they_have(self):
        """The chapter is the sharing boundary, and material is the thing it
        exists to share."""
        self.a_line()
        self.sign_in(self.eric.user)

        response = self.client.get("/org/ouat/")
        self.assertContains(response, "Reclaimed oak, mostly 2x8")
        self.assertContains(response, "board-feet")

    def test_no_value_appears_beside_it(self):
        """no-material-valuation, asserted at the surface as well as in the
        model. A quantity and a unit; never a price."""
        self.a_line()
        self.sign_in(self.eric.user)
        body = self.client.get("/org/ouat/").content.decode()

        section = body[body.index("What they have on hand"):]
        for forbidden in ("$", "value", "worth", "price", "each"):
            self.assertNotIn(forbidden, section.lower())

    def test_the_shelf_link_only_appears_on_your_own_page(self):
        """/warehouse/ lists the VIEWER's lines, so on a peer's page the
        link said "everything on hand" and showed somebody else's shelf."""
        self.a_line()

        # Scoped to the section. The nav shell links /warehouse/ on every
        # page — "On hand" is one of the six areas — so a bare assertion here
        # tests the navigation, not this block. That is the sixth time in
        # this codebase; when a page assertion could match the shell, scope
        # it to the section.
        def shelf(user):
            self.sign_in(user)
            body = self.client.get("/org/ouat/").content.decode()
            return body[body.index("What they have on hand"):]

        self.assertNotIn('href="/warehouse/"', shelf(self.eric.user))
        self.assertIn('href="/warehouse/"', shelf(self.hannah.user))

    def test_a_line_nobody_offers_does_not_show(self):
        line = self.a_line()
        with tenant_context(self.ouat):
            type(line).objects.filter(pk=line.pk).update(available=False)

        self.sign_in(self.eric.user)
        self.assertNotContains(self.client.get("/org/ouat/"),
                               "Reclaimed oak, mostly 2x8")
