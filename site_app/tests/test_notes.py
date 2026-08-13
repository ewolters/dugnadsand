"""Saying something, without asking or offering.

A community that can only ask and offer is a transaction desk with a nice
tone of voice. A note is somebody saying hello, that the food bank is shut on
Monday, or thank you for Saturday.

Everything below is about what a note does NOT do. It asks nothing, so there
is nothing to take up — and the interface must not imply otherwise, because a
claim on a hello puts somebody on the hook for it.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from site_app.models import Claim, Member, Organization, Posting, Region
from site_app.tenancy import set_tenant, tenant_context

from .helpers import SignedIn


class NoteBase(SignedIn, TestCase):
    def setUp(self):
        self.chapter = Region.objects.create(slug="up", name="Upstate")
        self.org = Organization.objects.create(
            slug="alpha", name="Alpha", region=self.chapter)
        self.user = User.objects.create_user("ada", password="dugnad-test-pw")
        self.other_user = User.objects.create_user("ola", password="dugnad-test-pw")
        with tenant_context(self.org):
            self.ada = Member.objects.create(
                organization=self.org, display_name="Ada", user=self.user)
            self.ola = Member.objects.create(
                organization=self.org, display_name="Ola", user=self.other_user)
            self.note = Posting.objects.create(
                organization=self.org, member=self.ola, kind=Posting.NOTE,
                description="Hello everyone — the food bank is shut Monday.")
        set_tenant(None)
        self.sign_in(self.user)

    def tearDown(self):
        set_tenant(None)


class PostingOne(NoteBase):
    def test_a_member_can_post_one(self):
        response = self.client.post("/board/new/", {
            "kind": "note", "description": "Thanks to everybody on Saturday.",
            "project": "", "needed_by": "", "hours_cap": ""})
        self.assertEqual(response.status_code, 302)

        with tenant_context(self.org):
            written = Posting.objects.get(description__startswith="Thanks")
        self.assertTrue(written.is_note)

    def test_the_form_offers_it_in_plain_words(self):
        body = self.client.get("/board/new/").content.decode()
        # Not the apostrophe — Django escapes it to &#x27; and the assertion
        # would be about HTML entities rather than about the words.
        self.assertIn("just saying something", body)

    def test_a_deadline_and_a_size_are_dropped(self):
        """Both fields are optional and somebody could fill them in before
        choosing "just saying". Left set, a hello would render an urgency
        chip and a rough number of hours."""
        self.client.post("/board/new/", {
            "kind": "note", "description": "Shut Monday.", "project": "",
            "needed_by": (timezone.localdate() + timedelta(days=2)).isoformat(),
            "hours_cap": "5"})

        with tenant_context(self.org):
            written = Posting.objects.get(description="Shut Monday.")
        self.assertIsNone(written.needed_by)
        self.assertIsNone(written.hours_cap)


class ItAsksNothing(NoteBase):
    def test_claiming_one_is_refused_by_the_service(self):
        """Refused where the rule lives, not just hidden in the template."""
        from site_app.services import claim_posting

        with tenant_context(self.org):
            with self.assertRaises(ValueError) as caught:
                claim_posting(posting=self.note, member=self.ada)
        self.assertIn("nothing to take up", str(caught.exception))

    def test_claiming_one_by_url_creates_nothing(self):
        self.client.post(f"/board/{self.note.id}/claim/")
        with tenant_context(self.org):
            self.assertEqual(Claim.objects.filter(posting=self.note).count(), 0)

    def test_the_card_offers_no_way_to_take_it_up(self):
        body = self.client.get("/community/").content.decode()
        self.assertNotIn(f'action="/board/{self.note.id}/claim/"', body)
        self.assertNotIn(f'action="/board/{self.note.id}/interested/"', body)
        self.assertNotIn(f'href="/board/{self.note.id}/hours/"', body)


class ItIsStillSomethingToTalkAbout(NoteBase):
    def test_it_appears_in_the_feed(self):
        self.assertContains(self.client.get("/community/"), "food bank is shut")

    def test_the_card_says_what_it_is(self):
        self.assertContains(self.client.get("/community/"), "saying")

    def test_it_has_its_own_page_and_a_reply_box(self):
        body = self.client.get(f"/board/{self.note.id}/").content.decode()
        self.assertIn("food bank is shut", body)
        self.assertIn('action="/comment/"', body)

    def test_somebody_can_reply_to_it(self):
        """The whole point of the thing."""
        from site_app.models import Comment

        self.client.post("/comment/", {
            "posting": str(self.note.id), "body": "Thanks for the heads up."})
        with tenant_context(self.org):
            self.assertEqual(Comment.objects.filter(posting=self.note).count(), 1)

    def test_the_saying_tab_finds_it(self):
        body = self.client.get("/community/?show=saying").content.decode()
        self.assertIn("food bank is shut", body)

    def test_the_asking_tab_does_not(self):
        body = self.client.get("/community/?show=asking").content.decode()
        self.assertNotIn("food bank is shut", body)

    def test_its_author_can_still_take_it_down(self):
        self.sign_in(self.other_user)
        self.client.post(f"/board/{self.note.id}/close/")
        with tenant_context(self.org):
            self.assertFalse(Posting.objects.get(pk=self.note.pk).open)
