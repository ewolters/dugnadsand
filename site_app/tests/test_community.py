"""The community: one feed, and a posting with a conversation on it.

Social in shape, and deliberately not in the part that ranks people. There is
no count beside anybody's name, no reaction, and no ordering that consults who
wrote a thing — so the tests here spend as much effort on what the feed must
never grow as on what it shows.
"""

import re
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase

from site_app.models import Comment, Member, Organization, Posting, Region
from site_app.services_social import add_comment
from site_app.tenancy import set_tenant, tenant_context

from .helpers import SignedIn


class CommunityBase(SignedIn, TestCase):
    def setUp(self):
        self.chapter = Region.objects.create(slug="upstate-wnc",
                                             name="Upstate SC and WNC")
        self.org = Organization.objects.create(
            slug="alpha", name="Alpha", region=self.chapter)
        self.user = User.objects.create_user("ada", password="dugnad-test-pw")
        self.other_user = User.objects.create_user("ola", password="dugnad-test-pw")
        with tenant_context(self.org):
            self.ada = Member.objects.create(
                organization=self.org, display_name="Ada", user=self.user)
            self.ola = Member.objects.create(
                organization=self.org, display_name="Ola", user=self.other_user)
            self.offer = Posting.objects.create(
                organization=self.org, member=self.ola, kind=Posting.OFFER,
                description="A ladder, free to borrow.")
            self.need = Posting.objects.create(
                organization=self.org, member=self.ola, kind=Posting.NEED,
                description="A ride to the clinic on Thursday.",
                needed_by=date.today() + timedelta(days=2))
        set_tenant(None)

    def tearDown(self):
        set_tenant(None)


class TheFeed(CommunityBase):
    def test_it_is_reachable_by_the_name_people_use(self):
        self.sign_in(self.user)
        self.assertEqual(self.client.get("/community/").status_code, 200)

    def test_the_old_address_still_works(self):
        """Every existing link, bookmark and POST target points at /board/."""
        self.sign_in(self.user)
        self.assertEqual(self.client.get("/board/").status_code, 200)

    def test_offers_and_needs_are_one_stream(self):
        """Not two headed lists. A reader sees a single run of what is
        happening, with the direction on each card."""
        self.sign_in(self.user)
        body = self.client.get("/community/").content.decode()
        self.assertIn("A ladder, free to borrow.", body)
        self.assertIn("A ride to the clinic", body)
        self.assertNotIn("<h2>People are asking for</h2>", body)

    def test_each_post_says_which_direction_it_is(self):
        self.sign_in(self.user)
        body = self.client.get("/community/").content.decode()
        self.assertIn("asking", body)
        self.assertIn("offering", body)

    def test_a_post_links_to_its_own_page(self):
        self.sign_in(self.user)
        body = self.client.get("/community/").content.decode()
        self.assertIn(f'/board/{self.need.id}/', body)

    def test_the_reply_count_appears_once_there_are_replies(self):
        with tenant_context(self.org):
            add_comment(member=self.ada, posting=self.need, body="I can drive.")
        self.sign_in(self.user)
        body = self.client.get("/community/").content.decode()
        self.assertIn("1 reply", body)

    def test_nothing_on_the_feed_counts_a_person(self):
        """The line between social and scored. A number beside a name is a
        score however it is labelled, and this system has none.

        Asserted against RENDERED TEXT, with the stylesheet and the tags
        stripped. The first version read the raw response and matched
        "points" inside a CSS comment — the same failure as "126" matching a
        UUID and "Bo" matching the nav label "Board".
        """
        import html as html_mod

        with tenant_context(self.org):
            add_comment(member=self.ada, posting=self.need, body="I can drive.")
        self.sign_in(self.user)

        raw = self.client.get("/community/").content.decode()
        raw = re.sub(r"<(script|style)\b.*?</\1>", " ", raw, flags=re.S | re.I)
        text = html_mod.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))).lower()

        for forbidden in ("posts", "karma", "reputation", "points", "streak",
                          "followers", "following", "likes", "upvote"):
            self.assertNotIn(forbidden, text, forbidden)

    def test_the_ordering_contract_is_unchanged(self):
        """The feed is one stream, but a dated need still leads an undated one
        and ordering still never consults the person."""
        with tenant_context(self.org):
            Posting.objects.create(
                organization=self.org, member=self.ada, kind=Posting.NEED,
                description="Undated need, posted latest.")
        self.sign_in(self.user)
        body = self.client.get("/community/").content.decode()
        self.assertLess(body.index("A ride to the clinic"),
                        body.index("Undated need"))
        self.assertLess(body.index("Undated need"),
                        body.index("A ladder, free to borrow."))


class ThePostingView(CommunityBase):
    def test_a_posting_has_a_page(self):
        self.sign_in(self.user)
        response = self.client.get(f"/board/{self.need.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A ride to the clinic")

    def test_the_conversation_is_shown_there(self):
        """THE GAP THIS CLOSES. A comment on a posting attached to a project
        appeared on the project page; a comment on a posting attached to
        nothing was written, stored, and displayed nowhere at all."""
        with tenant_context(self.org):
            add_comment(member=self.ada, posting=self.need,
                        body="I can drive her, I finish at two.")
        self.sign_in(self.user)
        self.assertContains(self.client.get(f"/board/{self.need.id}/"),
                            "I finish at two")

    def test_commenting_returns_to_the_posting_rather_than_the_board(self):
        self.sign_in(self.user)
        response = self.client.post("/comment/", {
            "posting": str(self.need.id), "body": "On my way."})
        self.assertRedirects(response, f"/board/{self.need.id}/",
                             fetch_redirect_response=False)

    def test_a_comment_on_a_posting_with_no_project_is_now_readable(self):
        """The exact case that vanished: no project, so nowhere to show it."""
        self.assertIsNone(self.need.project_id)
        self.sign_in(self.user)
        self.client.post("/comment/", {
            "posting": str(self.need.id), "body": "Two o'clock works."})

        with tenant_context(self.org):
            self.assertEqual(Comment.objects.filter(posting=self.need).count(), 1)
        self.assertContains(self.client.get(f"/board/{self.need.id}/"),
                            "Two o&#x27;clock works.")

    def test_it_can_be_claimed_from_its_own_page(self):
        self.sign_in(self.user)
        self.client.post(f"/board/{self.need.id}/claim/")
        self.assertContains(self.client.get(f"/board/{self.need.id}/"), "Ada")

    def test_a_closed_posting_still_reads_but_offers_no_actions(self):
        """A conversation does not stop being worth reading because the thing
        was taken down."""
        with tenant_context(self.org):
            self.need.open = False
            self.need.save(update_fields=["open"])
            add_comment(member=self.ada, posting=self.need, body="Sorted.")

        self.sign_in(self.user)
        body = self.client.get(f"/board/{self.need.id}/").content.decode()
        self.assertIn("Sorted.", body)
        self.assertIn("Taken down.", body)
        self.assertNotIn(f'action="/board/{self.need.id}/claim/"', body)

    def test_a_posting_from_another_chapter_is_not_reachable(self):
        midlands = Region.objects.create(slug="midlands", name="Midlands")
        far = Organization.objects.create(slug="far", name="Far", region=midlands)
        with tenant_context(far):
            member = Member.objects.create(organization=far, display_name="Sam")
            theirs = Posting.objects.create(
                organization=far, member=member, kind=Posting.OFFER,
                description="Not in this chapter.")
        set_tenant(None)

        self.sign_in(self.user)
        self.assertEqual(self.client.get(f"/board/{theirs.id}/").status_code, 404)

    def test_a_chapter_mate_in_another_organization_can_open_it(self):
        neighbour = Organization.objects.create(
            slug="beta", name="Beta", region=self.chapter)
        neighbour_user = User.objects.create_user("bo", password="dugnad-test-pw")
        with tenant_context(neighbour):
            Member.objects.create(organization=neighbour, display_name="Bo",
                                  user=neighbour_user)
        set_tenant(None)

        self.sign_in(neighbour_user)
        self.assertEqual(
            self.client.get(f"/board/{self.need.id}/").status_code, 200)


class TheNavSaysCommunity(CommunityBase):
    def test_the_area_is_named_for_what_it_is(self):
        self.sign_in(self.user)
        body = self.client.get("/community/").content.decode()
        self.assertRegex(body, r'aria-current="page"[^>]*>Community<')

    def test_the_page_is_titled_the_community(self):
        self.sign_in(self.user)
        self.assertContains(self.client.get("/community/"), "<h1>The community</h1>")
