"""The chapter is the sharing boundary, not the organization.

A mutual aid network is many organizations, most of them one or two people.
Two neighbours in one chapter being as invisible to each other as two
strangers in different states is the network not existing — you would have to
share an employer to talk about the work.

So there are three cases here and all three matter:

  same chapter        they see each other
  different chapters  they do not
  no chapter at all   they do not, exactly as before

The third is what keeps this from being a loosening. An organization admitted
into no chapter is scoped precisely as it was, which is also why every test
written before this change still passes: their fixtures create chapterless
organizations.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from site_app.models import (Contribution, Member, Organization, Posting,
                             Project, Region)
from site_app.tenancy import set_tenant, tenant_context

from .helpers import SignedIn


class ChapterBase(SignedIn, TestCase):
    def setUp(self):
        self.upstate = Region.objects.create(slug="upstate-wnc",
                                             name="Upstate SC and WNC")
        self.midlands = Region.objects.create(slug="midlands", name="Midlands")

        # Two one-person organizations in the same chapter. This is the normal
        # shape of the network, not an edge case.
        self.hers = Organization.objects.create(
            slug="ouat", name="Once Upon a Table", region=self.upstate)
        self.his = Organization.objects.create(
            slug="svend", name="SVEND", region=self.upstate)
        self.far = Organization.objects.create(
            slug="rivertown", name="Rivertown", region=self.midlands)

        self.hannah_user = User.objects.create_user("hannah", password="dugnad-test-pw")
        self.eric_user = User.objects.create_user("eric", password="dugnad-test-pw")
        self.far_user = User.objects.create_user("sam", password="dugnad-test-pw")

        with tenant_context(self.hers):
            self.hannah = Member.objects.create(
                organization=self.hers, display_name="Hannah", user=self.hannah_user)
            self.her_posting = Posting.objects.create(
                organization=self.hers, member=self.hannah, kind=Posting.OFFER,
                description="Unlimited weekly bus pass for Greenlink.")
        with tenant_context(self.his):
            self.eric = Member.objects.create(
                organization=self.his, display_name="Eric", user=self.eric_user)
            self.his_project = Project.objects.create(
                organization=self.his, started_by=self.eric,
                name="Dugnadsand Initiation", description="Getting started.")
        with tenant_context(self.far):
            self.sam = Member.objects.create(
                organization=self.far, display_name="Sam", user=self.far_user)
            self.far_posting = Posting.objects.create(
                organization=self.far, member=self.sam, kind=Posting.OFFER,
                description="A ladder in the Midlands.")
        set_tenant(None)

    def tearDown(self):
        set_tenant(None)


class NeighboursInAChapterSeeEachOther(ChapterBase):
    def test_she_sees_his_project_on_the_board(self):
        self.sign_in(self.hannah_user)
        self.assertContains(self.client.get("/projects/"), "Dugnadsand Initiation")

    def test_he_sees_her_posting(self):
        self.sign_in(self.eric_user)
        self.assertContains(self.client.get("/board/"), "Greenlink")

    def test_he_can_open_her_posting_and_claim_it(self):
        """Seeing it is not enough. The whole point is being able to take it
        up — a board you can read and not act on is a noticeboard."""
        self.sign_in(self.eric_user)
        response = self.client.post(f"/board/{self.her_posting.id}/claim/")
        self.assertEqual(response.status_code, 302)

    def test_a_project_page_from_a_chapter_mate_opens(self):
        self.sign_in(self.hannah_user)
        self.assertEqual(
            self.client.get(f"/projects/{self.his_project.id}/").status_code, 200)

    def test_the_ledger_shows_the_chapter_not_just_the_organization(self):
        from site_app.services import record_contribution

        with tenant_context(self.hers):
            record_contribution(member=self.hannah, posting=self.her_posting,
                                hours=Decimal("2.00"), note="Rode along.")
        self.sign_in(self.eric_user)
        self.assertContains(self.client.get("/ledger/"), "Hannah")


class OtherChaptersStayInvisible(ChapterBase):
    def test_the_midlands_posting_does_not_appear(self):
        self.sign_in(self.eric_user)
        self.assertNotContains(self.client.get("/board/"), "Midlands")

    def test_it_cannot_be_reached_by_url_either(self):
        self.sign_in(self.eric_user)
        self.assertEqual(
            self.client.post(f"/board/{self.far_posting.id}/claim/").status_code, 404)

    def test_and_the_reverse(self):
        self.sign_in(self.far_user)
        self.assertNotContains(self.client.get("/board/"), "Greenlink")


class AnOrganizationInNoChapterIsScopedAsBefore(ChapterBase):
    """The property that makes this a change of boundary rather than a
    loosening — and the reason every test written before it still passes."""

    def setUp(self):
        super().setUp()
        self.loose_a = Organization.objects.create(slug="a", name="Alpha")
        self.loose_b = Organization.objects.create(slug="b", name="Beta")
        self.loose_user = User.objects.create_user("ada", password="dugnad-test-pw")
        with tenant_context(self.loose_a):
            self.ada = Member.objects.create(
                organization=self.loose_a, display_name="Ada", user=self.loose_user)
        with tenant_context(self.loose_b):
            b_member = Member.objects.create(
                organization=self.loose_b, display_name="Bo")
            Posting.objects.create(
                organization=self.loose_b, member=b_member, kind=Posting.OFFER,
                description="Two crates of potatoes.")
        set_tenant(None)

    def test_two_chapterless_organizations_cannot_see_each_other(self):
        self.sign_in(self.loose_user)
        self.assertNotContains(self.client.get("/board/"), "potatoes")

    def test_nor_can_a_chapterless_one_see_into_a_chapter(self):
        self.sign_in(self.loose_user)
        self.assertNotContains(self.client.get("/board/"), "Greenlink")

    def test_nor_a_chapter_member_see_the_chapterless(self):
        self.sign_in(self.eric_user)
        self.assertNotContains(self.client.get("/board/"), "potatoes")

    def test_an_empty_region_setting_matches_nothing(self):
        """NULLIF(..., '') IS NOT NULL is load-bearing. Without it an empty
        chapter setting compares NULL against every row's region and the
        policy would depend on NULL semantics nobody wants to reason about."""
        from site_app.tenancy import set_tenant

        set_tenant(self.loose_a.id, region_id=None)
        self.assertEqual(Posting.objects.count(), 0)


class WritesStayWithTheirOwner(ChapterBase):
    def test_a_posting_written_here_belongs_to_this_organization(self):
        """Visibility widened; ownership did not. Hannah's posting is still
        Hannah's, and Eric writing on the shared board writes into SVEND."""
        self.sign_in(self.eric_user)
        self.client.post("/board/new/", {
            "kind": "offer", "description": "Half a Saturday and a truck.",
            "hours_cap": "4"})

        with tenant_context(self.his):
            written = Posting.objects.get(description__startswith="Half a Saturday")
        self.assertEqual(written.organization_id, self.his.id)
        self.assertEqual(written.member_id, self.eric.id)

    def test_a_contribution_is_recorded_against_the_member_who_gave_it(self):
        from site_app.services import record_contribution

        with tenant_context(self.his):
            record_contribution(member=self.eric, posting=self.her_posting,
                                hours=Decimal("3.00"), note="Across the chapter.")
            entry = Contribution.objects.get(member=self.eric)
        self.assertEqual(entry.organization_id, self.his.id)
        self.assertEqual(entry.posting_id, self.her_posting.id)
