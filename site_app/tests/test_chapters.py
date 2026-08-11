"""The chapter screens.

The map is the easy half. The half worth testing is that the officer screen
shows a roster and cannot be made to show anything inside an organization --
including when the officer is also a member of one, which is the case that
would slip through: Eric is an officer of Upstate SC and a member of SVEND,
and the two must not leak into each other on this page.
"""

from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from site_app.models import (Application, Member, Organization, Posting,
                             Region, RegionRole)
from site_app.services_applications import record_screening, submit
from site_app.tenancy import set_tenant, tenant_context

from .helpers import SignedIn


class ChapterScreenBase(SignedIn, TestCase):
    def setUp(self):
        self.upstate = Region.objects.create(
            slug="upstate-sc", name="Upstate, SC",
            covers="Greenville, Spartanburg, Anderson and the counties around them.",
            map_areas="greenville,spartanburg,anderson,pickens,oconee")
        self.org = Organization.objects.create(
            slug="alpha", name="Alpha Mutual Aid", region=self.upstate)

        self.officer = User.objects.create_user(
            "eric", email="eric@example.test", password="dugnad-test-pw")
        RegionRole.objects.create(region=self.upstate, user=self.officer,
                                  role=RegionRole.LEAD, title="Officer")

        self.member_user = User.objects.create_user(
            "ada", password="dugnad-test-pw")
        with tenant_context(self.org):
            self.member = Member.objects.create(
                organization=self.org, display_name="Ada", user=self.member_user)
            self.posting = Posting.objects.create(
                organization=self.org, member=self.member,
                description="A confidential thing on the board.")
        set_tenant(None)

    def tearDown(self):
        set_tenant(None)


class ThePublicMap(ChapterScreenBase):
    def test_it_is_public(self):
        self.assertEqual(self.client.get("/chapters/").status_code, 200)

    def test_the_covered_counties_are_shaded_in_the_html(self):
        """Server-side, so a visitor with no JavaScript does not see an empty
        state and read it as "no chapters anywhere"."""
        body = self.client.get("/chapters/").content.decode()
        self.assertIn('id="c-greenville" class="county held"', body)

    def test_an_uncovered_county_is_not_shaded(self):
        body = self.client.get("/chapters/").content.decode()
        self.assertIn('id="c-charleston" class="county"', body)
        self.assertNotIn('id="c-charleston" class="county held"', body)

    def test_every_county_is_named_for_a_reader_who_cannot_see_colour(self):
        body = self.client.get("/chapters/").content.decode()
        self.assertIn("<title>Greenville — Upstate, SC</title>", body)
        self.assertIn("<title>Charleston — no chapter yet</title>", body)

    def test_it_says_how_much_of_the_state_is_covered(self):
        body = self.client.get("/chapters/").content.decode()
        self.assertIn("5 of 46 counties", body)

    def test_the_map_needs_nothing_from_anywhere_else(self):
        """A tile provider would receive the address of every visitor who
        looks at this page."""
        import re

        body = self.client.get("/chapters/").content.decode()
        external = re.findall(r'(?:src|href)="(https?://[^"]+)"', body)
        external = [u for u in external if "dugnadsand.org" not in u]
        self.assertEqual(external, [], f"the page reaches out to {external}")

    def test_it_names_the_chapter_without_naming_anybody_in_it(self):
        body = self.client.get("/chapters/").content.decode()
        self.assertIn("Upstate, SC", body)
        self.assertNotIn("Ada", body)
        self.assertNotIn("confidential thing", body)


class TheOfficerScreen(ChapterScreenBase):
    def test_an_officer_can_reach_it(self):
        self.sign_in(self.officer)
        self.assertEqual(self.client.get("/chapter/").status_code, 200)

    def test_somebody_with_no_role_cannot(self):
        self.sign_in(self.member_user)
        self.assertEqual(self.client.get("/chapter/").status_code, 403)

    def test_a_signed_out_visitor_cannot(self):
        response = self.client.get("/chapter/")
        self.assertNotEqual(response.status_code, 200)

    def test_it_lists_the_organizations_by_name_only(self):
        self.sign_in(self.officer)
        body = self.client.get("/chapter/").content.decode()
        self.assertIn("Alpha Mutual Aid", body)

    def test_it_shows_nothing_from_inside_an_organization(self):
        """The claim the whole chapter design rests on. An officer sees that
        Alpha exists, never what is on Alpha's board or who is in it."""
        self.sign_in(self.officer)
        body = self.client.get("/chapter/").content.decode()
        for leaked in ("confidential thing", "Ada"):
            self.assertNotIn(leaked, body, leaked)

    def test_it_lists_the_other_officers(self):
        other = User.objects.create_user("hannah", password="dugnad-test-pw")
        RegionRole.objects.create(region=self.upstate, user=other,
                                  role=RegionRole.LEAD, title="Officer")
        self.sign_in(self.officer)
        self.assertIn("hannah", self.client.get("/chapter/").content.decode())

    def test_it_shows_applications_waiting_and_what_each_needs(self):
        self.sign_in(self.officer)
        submit(kind=Application.BUSINESS, region=self.upstate,
               legal_name="Alderman Electric LLC", contact_name="Dana",
               email="dana@example.test", statement="We wire things.",
               agreed=True)

        body = self.client.get("/chapter/").content.decode()
        self.assertIn("Alderman Electric LLC", body)
        self.assertIn("Business license not verified", body)

    def test_an_application_to_another_chapter_is_not_shown(self):
        elsewhere = Region.objects.create(slug="midlands", name="Midlands")
        submit(kind=Application.NONPROFIT, region=elsewhere,
               legal_name="Somebody Else Trust", contact_name="Sam",
               email="sam@example.test", statement="Elsewhere.", agreed=True)

        self.sign_in(self.officer)
        self.assertNotIn("Somebody Else Trust",
                         self.client.get("/chapter/").content.decode())

    def test_a_ready_application_says_so(self):
        self.sign_in(self.officer)
        application = submit(
            kind=Application.INDIVIDUAL, region=self.upstate,
            legal_name="Ola Nilsen", contact_name="Ola Nilsen",
            email="ola@example.test", statement="A truck.", agreed=True)
        record_screening(application=application, user=self.officer,
                         source="A registry", searched_name="Ola Nilsen",
                         searched_on=date.today(), clear=True)

        self.assertIn("Ready to decide.",
                      self.client.get("/chapter/").content.decode())

    def test_an_officer_who_is_also_a_member_sees_no_more(self):
        """The case that would slip through. Holding both a chapter role and a
        membership must not join them: the officer's own organization is not a
        window into anybody else's, and their membership grants this page
        nothing it would not otherwise show.
        """
        with tenant_context(self.org):
            Member.objects.create(organization=self.org, display_name="Eric",
                                  user=self.officer)
        set_tenant(None)

        self.sign_in(self.officer)
        body = self.client.get("/chapter/").content.decode()
        for leaked in ("confidential thing", "Ada"):
            self.assertNotIn(leaked, body, leaked)

    def test_the_page_states_what_it_cannot_show(self):
        import re

        self.sign_in(self.officer)
        body = re.sub(r"\s+", " ", self.client.get("/chapter/").content.decode())
        self.assertIn("no access to anything inside the organizations", body)
