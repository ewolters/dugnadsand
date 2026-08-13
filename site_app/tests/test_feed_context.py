"""What a card says about who posted, when, and how to narrow the feed.

The chapter is the boundary, so a reader sees postings from several
organizations at once. A name on its own does not say whether this is a
neighbour, a business or a not-for-profit — and in a network whose whole
premise is that those are different kinds of party, that is the missing half
of the sentence.
"""

import re
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from site_app.models import Member, Organization, Posting, Region
from site_app.tenancy import set_tenant, tenant_context

from .helpers import SignedIn


class FeedBase(SignedIn, TestCase):
    def setUp(self):
        self.chapter = Region.objects.create(slug="up", name="Upstate")
        self.mine = Organization.objects.create(
            slug="svend", name="SVEND", region=self.chapter)
        self.theirs = Organization.objects.create(
            slug="ouat", name="Once Upon a Table", region=self.chapter)

        self.user = User.objects.create_user("eric", password="dugnad-test-pw")
        with tenant_context(self.mine):
            self.eric = Member.objects.create(
                organization=self.mine, display_name="Eric", user=self.user)
            self.my_offer = Posting.objects.create(
                organization=self.mine, member=self.eric, kind=Posting.OFFER,
                description="A cement mixer, free to borrow.")
        with tenant_context(self.theirs):
            self.hannah = Member.objects.create(
                organization=self.theirs, display_name="Hannah")
            self.their_need = Posting.objects.create(
                organization=self.theirs, member=self.hannah, kind=Posting.NEED,
                description="Volunteers to clean inventory.")
        set_tenant(None)
        self.sign_in(self.user)

    def tearDown(self):
        set_tenant(None)

    def feed(self, query=""):
        return self.client.get("/community/" + query).content.decode()


class ACardSaysWhichOrganization(FeedBase):
    def test_the_organization_appears_beside_the_name(self):
        body = self.feed()
        self.assertIn("Once Upon a Table", body)
        self.assertIn("SVEND", body)

    def test_it_appears_on_the_posting_page_too(self):
        body = self.client.get(f"/board/{self.their_need.id}/").content.decode()
        self.assertIn("Once Upon a Table", body)

    def test_the_organization_is_joined_rather_than_fetched_per_card(self):
        """Without the join the feed runs one query per posting — the shape
        that only hurts once a chapter is busy, which is the moment it
        matters. Asserted by adding postings and watching the count hold."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with tenant_context(self.theirs):
            for n in range(6):
                Posting.objects.create(
                    organization=self.theirs, member=self.hannah,
                    kind=Posting.OFFER, description=f"Spare thing {n}.")

        with CaptureQueriesContext(connection) as ctx:
            self.client.get("/community/")
        many = len(ctx.captured_queries)

        with tenant_context(self.theirs):
            Posting.objects.filter(description__startswith="Spare thing").delete()

        with CaptureQueriesContext(connection) as ctx:
            self.client.get("/community/")
        few = len(ctx.captured_queries)

        self.assertLessEqual(many - few, 1,
                             "the feed queries grow with the number of cards")


class TheTimeReadsAsTime(FeedBase):
    def test_a_recent_posting_reads_in_hours(self):
        with tenant_context(self.mine):
            Posting.objects.filter(pk=self.my_offer.pk).update(
                created_at=timezone.now() - timedelta(hours=3))
        self.assertIn("3h ago", self.feed())

    def test_an_old_one_falls_back_to_a_date(self):
        """Past a week the day of the month is more use than a count of
        weeks: "3w ago" and "24 Aug" answer different questions."""
        with tenant_context(self.mine):
            Posting.objects.filter(pk=self.my_offer.pk).update(
                created_at=timezone.now() - timedelta(days=40))
        body = self.feed()
        self.assertNotIn("40d ago", body)

    def test_something_just_posted_says_so(self):
        self.assertIn("just now", self.feed())


class TabsNarrowAndNeverRank(FeedBase):
    def test_everything_shows_both(self):
        body = self.feed()
        self.assertIn("cement mixer", body)
        self.assertIn("clean inventory", body)

    def test_asking_shows_only_needs(self):
        body = self.feed("?show=asking")
        self.assertIn("clean inventory", body)
        self.assertNotIn("cement mixer", body)

    def test_offering_shows_only_offers(self):
        body = self.feed("?show=offering")
        self.assertIn("cement mixer", body)
        self.assertNotIn("clean inventory", body)

    def test_mine_shows_only_my_own(self):
        body = self.feed("?show=mine")
        self.assertIn("cement mixer", body)
        self.assertNotIn("clean inventory", body)

    def test_an_unknown_filter_shows_everything(self):
        """A URL somebody edited must not empty the page."""
        body = self.feed("?show=banana")
        self.assertIn("cement mixer", body)
        self.assertIn("clean inventory", body)

    def test_a_filter_never_reorders_what_remains(self):
        """The ordering contract holds INSIDE every view. A tab narrows; it
        does not sort, and it never consults who asked."""
        with tenant_context(self.theirs):
            Posting.objects.create(
                organization=self.theirs, member=self.hannah, kind=Posting.NEED,
                description="Later need, no date.")
            Posting.objects.create(
                organization=self.theirs, member=self.hannah, kind=Posting.NEED,
                description="Dated need, soon.",
                needed_by=timezone.localdate() + timedelta(days=1))

        body = self.feed("?show=asking")
        self.assertLess(body.index("Dated need"), body.index("Later need"))

    def test_an_empty_filter_says_it_is_the_filter(self):
        """Not "nothing has happened here", which would be a lie about the
        chapter rather than a fact about the tab."""
        with tenant_context(self.mine):
            Posting.objects.filter(pk=self.my_offer.pk).update(open=False)
        body = self.feed("?show=offering")
        self.assertIn("Nothing here under that filter", body)

    def test_no_tab_counts_anything(self):
        """A number beside a tab is a score with a different label."""
        nav = re.search(r'<nav class="tabs".*?</nav>', self.feed(), re.S).group(0)
        self.assertNotRegex(nav, r"\d")
