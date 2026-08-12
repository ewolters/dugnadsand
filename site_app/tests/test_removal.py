"""Closing an organization, and removing one from a chapter.

Two different powers that were easy to confuse, so they are kept apart:

  active=False   the organization is shut. Nobody in it can see or post
                 anything anywhere. A network-level act.

  region=NULL    the organization leaves one chapter and is scoped to
                 itself, exactly as one admitted into no chapter has always
                 been. A chapter-level act, and the strongest thing an
                 officer can do to somebody else's organization.

Neither deletes anything, and the tests say so in both directions.
"""

from django.contrib.auth.models import User
from django.test import TestCase

from site_app.models import (ChapterRemoval, Member, Organization, Posting,
                             Region, RegionRole)
from site_app.services_applications import remove_from_chapter
from site_app.tenancy import set_tenant, tenant_context

from .helpers import SignedIn


class RemovalBase(SignedIn, TestCase):
    def setUp(self):
        self.chapter = Region.objects.create(slug="up", name="Upstate")
        self.mine = Organization.objects.create(
            slug="mine", name="Mine", region=self.chapter)
        self.theirs = Organization.objects.create(
            slug="theirs", name="Theirs", region=self.chapter)

        self.officer = User.objects.create_user("hannah", password="dugnad-test-pw")
        RegionRole.objects.create(region=self.chapter, user=self.officer,
                                  role=RegionRole.LEAD)
        self.member_user = User.objects.create_user("ada", password="dugnad-test-pw")

        with tenant_context(self.mine):
            Member.objects.create(organization=self.mine, display_name="Hannah",
                                  user=self.officer)
        with tenant_context(self.theirs):
            self.ada = Member.objects.create(
                organization=self.theirs, display_name="Ada", user=self.member_user)
            self.posting = Posting.objects.create(
                organization=self.theirs, member=self.ada, kind=Posting.OFFER,
                description="A ladder, free to borrow.")
        set_tenant(None)

    def tearDown(self):
        set_tenant(None)


class TheActiveFlagNowGates(RemovalBase):
    """It existed, looked like a switch, and gated nothing. Somebody flipping
    it would have believed something happened."""

    def close(self):
        Organization.objects.filter(pk=self.theirs.pk).update(active=False)

    def test_a_member_of_a_closed_organization_is_told(self):
        self.sign_in(self.member_user)
        self.assertEqual(self.client.get("/community/").status_code, 200)

        self.close()
        self.assertContains(self.client.get("/community/"),
                            "This organization is closed", status_code=403)

    def test_they_can_still_sign_out(self):
        """A closed door is not a locked room."""
        self.close()
        self.sign_in(self.member_user)
        self.assertEqual(self.client.post("/logout/").status_code, 302)

    def test_nothing_of_theirs_is_deleted(self):
        self.close()
        with tenant_context(self.theirs):
            self.assertEqual(Posting.objects.count(), 1)

    def test_others_stop_seeing_it_too(self):
        self.close()
        self.sign_in(self.officer)
        self.assertNotContains(self.client.get("/community/"), "A ladder")

    def test_an_open_organization_is_unaffected(self):
        self.sign_in(self.member_user)
        self.assertEqual(self.client.get("/community/").status_code, 200)


class RemovingFromAChapter(RemovalBase):
    def test_an_officer_can_remove_an_organization(self):
        self.sign_in(self.officer)
        self.client.post(f"/chapter/remove/{self.theirs.id}/",
                         {"reason": "Repeated campaigning after being asked."})

        self.assertIsNone(Organization.objects.get(pk=self.theirs.pk).region)

    def test_the_removal_is_recorded_with_who_and_why(self):
        """A strongest remedy that leaves no trace is one nobody can be asked
        about afterwards."""
        self.sign_in(self.officer)
        self.client.post(f"/chapter/remove/{self.theirs.id}/",
                         {"reason": "Repeated campaigning after being asked."})

        record = ChapterRemoval.objects.get(organization=self.theirs)
        self.assertEqual(record.removed_by, self.officer)
        self.assertEqual(record.region, self.chapter)
        self.assertIn("campaigning", record.reason)

    def test_a_removal_with_no_reason_is_refused(self):
        self.sign_in(self.officer)
        self.client.post(f"/chapter/remove/{self.theirs.id}/", {"reason": "  "})

        self.assertEqual(Organization.objects.get(pk=self.theirs.pk).region,
                         self.chapter)
        self.assertEqual(ChapterRemoval.objects.count(), 0)

    def test_the_chapter_stops_seeing_their_work(self):
        self.sign_in(self.officer)
        self.assertContains(self.client.get("/community/"), "A ladder")

        self.client.post(f"/chapter/remove/{self.theirs.id}/",
                         {"reason": "Out of area."})
        self.assertNotContains(self.client.get("/community/"), "A ladder")

    def test_and_they_stop_seeing_the_chapter(self):
        self.sign_in(self.officer)
        self.client.post(f"/chapter/remove/{self.theirs.id}/",
                         {"reason": "Out of area."})

        self.sign_in(self.member_user)
        self.assertNotContains(self.client.get("/community/"), "Mine")

    def test_NOTHING_IS_DELETED_and_they_keep_their_login(self):
        """Removal from a room is not erasure from the record."""
        self.sign_in(self.officer)
        self.client.post(f"/chapter/remove/{self.theirs.id}/",
                         {"reason": "Out of area."})

        self.sign_in(self.member_user)
        response = self.client.get("/community/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A ladder")

    def test_a_non_officer_cannot(self):
        self.sign_in(self.member_user)
        response = self.client.post(f"/chapter/remove/{self.theirs.id}/",
                                    {"reason": "I would rather they left."})
        self.assertEqual(response.status_code, 403)
        self.assertIsNotNone(Organization.objects.get(pk=self.theirs.pk).region)

    def test_an_officer_of_another_chapter_cannot(self):
        elsewhere = Region.objects.create(slug="mid", name="Midlands")
        stranger = User.objects.create_user("sam", password="dugnad-test-pw")
        RegionRole.objects.create(region=elsewhere, user=stranger,
                                  role=RegionRole.LEAD)

        self.sign_in(stranger)
        response = self.client.post(f"/chapter/remove/{self.theirs.id}/",
                                    {"reason": "Not my chapter."})
        self.assertEqual(response.status_code, 403)

    def test_removing_one_already_gone_is_refused_rather_than_recorded_twice(self):
        self.sign_in(self.officer)
        self.client.post(f"/chapter/remove/{self.theirs.id}/", {"reason": "Once."})
        self.client.post(f"/chapter/remove/{self.theirs.id}/", {"reason": "Twice."})
        self.assertEqual(ChapterRemoval.objects.count(), 1)
