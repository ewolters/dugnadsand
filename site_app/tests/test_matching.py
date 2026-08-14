"""Getting the right help to the right people, when it is needed.

The board was correct long before it was useful. A need could sit open for a
week because the two people who could have met it never happened to log in on
the same day. These tests cover the part that closes that gap — and, more
importantly, they pin the three ways it could close it wrongly:

  * by choosing recipients from the ledger (gating, wearing a delivery list)
  * by carrying tenant text out to the shared platform database (an RLS hole
    that no policy in Postgres can see, because it is on the other side)
  * by making a notice into an obligation

Everything below asserts mechanism. Where a test needs to know what a member
sees, it reads the form fields or the ordering, never the prose — copy is
rewritten often and a test that greps sentences fails for the wrong reasons.
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from site_app.models import Member, Organization, Posting
from site_app.notifications import _audience, announce_claim, announce_posting
from site_app.tenancy import tenant_context

from .helpers import SignedIn


class MatchingBase(SignedIn, TestCase):
    """Two organizations. In alpha, three people who can be reached."""

    def setUp(self):
        self.alpha = Organization.objects.create(slug="alpha", name="Alpha Mutual Aid")
        self.beta = Organization.objects.create(slug="beta", name="Beta Mutual Aid")

        def member(org, username, name, email):
            user = User.objects.create_user(username, email=email,
                                            password="dugnad-test-pw")
            with tenant_context(org):
                return user, Member.objects.create(
                    organization=org, display_name=name, user=user)

        self.ada_user, self.ada = member(self.alpha, "ada", "Ada", "ada@example.test")
        self.ola_user, self.ola = member(self.alpha, "ola", "Ola", "ola@example.test")
        self.kit_user, self.kit = member(self.alpha, "kit", "Kit", "kit@example.test")
        self.bo_user, self.bo = member(self.beta, "bo", "Bo", "bo@example.test")

    def messages(self, mock):
        """(recipient, message) for every notice a mocked notify.send received."""
        return [(c.args[0], c.args[3]) for c in mock.call_args_list]

    def recipients(self, mock):
        return {c.args[0] for c in mock.call_args_list}

    def need(self, description="A ride to the clinic.", needed_by=None, member=None):
        with tenant_context(self.alpha):
            return Posting.objects.create(
                organization=self.alpha, member=member or self.ada,
                kind=Posting.NEED, description=description, needed_by=needed_by)


class WhoHears(MatchingBase):
    """Recipients are chosen by membership. By nothing else, ever."""

    def test_a_new_posting_reaches_everyone_else_in_the_organization(self):
        posting = self.need()
        with patch("kjerne_platform.notify.send") as send:
            with tenant_context(self.alpha):
                sent = announce_posting(posting)

        self.assertEqual(sent, 2)
        self.assertEqual(self.recipients(send),
                         {"ola@example.test", "kit@example.test"})

    def test_the_poster_is_not_told_about_their_own_posting(self):
        posting = self.need()
        with patch("kjerne_platform.notify.send") as send:
            with tenant_context(self.alpha):
                announce_posting(posting)
        self.assertNotIn("ada@example.test", self.recipients(send))

    def test_the_audience_never_depends_on_what_anyone_has_given(self):
        """The one that matters.

        Kit has given a great deal and Ola has given nothing at all. If the
        recipient list ever starts sorting, scoring or filtering on the ledger,
        the record has become standing and the whole model fails — see
        no-gating in policy/manifest.toml. Both must hear, identically.
        """
        from site_app.services import record_contribution

        with tenant_context(self.alpha):
            work = Posting.objects.create(
                organization=self.alpha, member=self.ada, kind=Posting.OFFER,
                description="Somewhere to put hours.")
            for _ in range(5):
                record_contribution(posting=work, member=self.kit,
                                    hours=Decimal("8.00"), note="")

        posting = self.need()
        with patch("kjerne_platform.notify.send") as send:
            with tenant_context(self.alpha):
                announce_posting(posting)

        by_recipient = dict(self.messages(send))
        self.assertEqual(set(by_recipient), {"ola@example.test", "kit@example.test"})
        # Same words to the person who gave 40 hours and the person who gave none.
        self.assertEqual(by_recipient["ola@example.test"],
                         by_recipient["kit@example.test"])

    def test_the_audience_query_does_not_touch_the_contribution_table(self):
        """Structural backstop for the test above.

        The behavioural test passes as long as the outcome is equal. This one
        fails the moment the query LEARNS about contributions at all, which is
        the change a future ranking feature would have to make first.
        """
        with tenant_context(self.alpha):
            sql = str(_audience(self.alpha.id).query).lower()
        self.assertNotIn("contribution", sql)
        self.assertNotIn("claim", sql)

    def test_another_organization_never_hears_anything(self):
        posting = self.need()
        with patch("kjerne_platform.notify.send") as send:
            with tenant_context(self.alpha):
                announce_posting(posting)
        self.assertNotIn("bo@example.test", self.recipients(send))

    def test_a_member_with_no_email_is_skipped_not_crashed_on(self):
        with tenant_context(self.alpha):
            Member.objects.create(organization=self.alpha, display_name="Unreachable")
        posting = self.need()
        with patch("kjerne_platform.notify.send") as send:
            with tenant_context(self.alpha):
                sent = announce_posting(posting)
        self.assertEqual(sent, 2)


class WhatTheNoticeCarries(MatchingBase):
    """kjerne_platform.notify writes to the SHARED platform database.

    Postgres RLS scopes site_app tables to one organization. It does not reach
    the platform notification table, which sits alongside every other
    federation site's notices. So anything placed in a notice body has left the
    tenant, and these tests are the only thing standing between a well-meaning
    "make the email more useful" change and a cross-tenant data leak.
    """

    def test_the_body_never_carries_the_posting_text(self):
        posting = self.need("Can someone drive my mother to dialysis Thursday")
        with patch("kjerne_platform.notify.send") as send:
            with tenant_context(self.alpha):
                announce_posting(posting)

        for _, message in self.messages(send):
            self.assertNotIn("dialysis", message)
            self.assertNotIn("mother", message)

    def test_the_body_never_carries_a_member_name(self):
        posting = self.need()
        with patch("kjerne_platform.notify.send") as send:
            with tenant_context(self.alpha):
                announce_posting(posting)
                announce_claim(self._claim(posting, self.ola))

        for _, message in self.messages(send):
            self.assertNotIn("Ada", message)
            self.assertNotIn("Ola", message)

    def test_the_body_does_carry_urgency_because_that_is_the_whole_point(self):
        posting = self.need(needed_by=date.today())
        with patch("kjerne_platform.notify.send") as send:
            with tenant_context(self.alpha):
                announce_posting(posting)
        self.assertIn("today", self.messages(send)[0][1])

    def test_every_notice_links_back_where_the_real_content_lives(self):
        posting = self.need()
        with patch("kjerne_platform.notify.send") as send:
            with tenant_context(self.alpha):
                announce_posting(posting)
        for call in send.call_args_list:
            self.assertEqual(call.kwargs["link"], "/board/")

    def _claim(self, posting, member):
        from site_app.services import claim_posting
        return claim_posting(posting=posting, member=member)


class TellingThePoster(MatchingBase):
    def test_a_claim_tells_the_poster_and_nobody_else(self):
        posting = self.need()
        with tenant_context(self.alpha):
            from site_app.services import claim_posting
            claim = claim_posting(posting=posting, member=self.ola)
            with patch("kjerne_platform.notify.send") as send:
                announce_claim(claim)

        self.assertEqual(self.recipients(send), {"ada@example.test"})

    def test_the_two_directions_read_differently(self):
        """On an offer the poster gives; on a need the poster receives. A
        notice that ignored the direction would tell somebody they were about
        to be helped when in fact they had just been asked for something."""
        from site_app.services import claim_posting

        with tenant_context(self.alpha):
            offer = Posting.objects.create(
                organization=self.alpha, member=self.ada, kind=Posting.OFFER,
                description="Two crates of potatoes.")
            need = Posting.objects.create(
                organization=self.alpha, member=self.ada, kind=Posting.NEED,
                description="A ride.")
            with patch("kjerne_platform.notify.send") as send:
                announce_claim(claim_posting(posting=offer, member=self.ola))
                announce_claim(claim_posting(posting=need, member=self.ola))

        offer_msg, need_msg = [m for _, m in self.messages(send)]
        self.assertNotEqual(offer_msg, need_msg)


class NoticesFailOpen(MatchingBase):
    """Posting help is the point. Being told is the service."""

    def test_a_broken_notice_service_does_not_lose_the_posting(self):
        self.sign_in(self.ada_user)
        with patch("kjerne_platform.notify.send", side_effect=RuntimeError("down")):
            response = self.client.post("/board/new/", {
                "kind": "offer", "description": "A ride to the clinic.",
                "needed_by": "", "hours_cap": ""})

        self.assertEqual(response.status_code, 302)
        with tenant_context(self.alpha):
            self.assertTrue(Posting.objects.filter(description__contains="clinic").exists())

    def test_a_broken_notice_service_does_not_lose_the_claim(self):
        from site_app.models import Claim

        posting = self.need()
        self.sign_in(self.ola_user)
        with patch("kjerne_platform.notify.send", side_effect=RuntimeError("down")):
            response = self.client.post(f"/board/{posting.id}/claim/")

        self.assertEqual(response.status_code, 302)
        with tenant_context(self.alpha):
            self.assertEqual(Claim.objects.filter(posting=posting).count(), 1)


class WhenItIsNeeded(MatchingBase):
    """Ordering is a fact about the need, never about who asked."""

    def feed_order(self):
        """The descriptions on the feed's cards, in the order they appear.

        These asserted on body.index() of the raw HTML, which broke the day
        the composer moved onto the feed: its "Needed by" help text reads "A
        ride on Thursday and a fence sometime this year are different
        things", so a search for "fence sometime" found the HELP TEXT above
        the feed and the ordering looked reversed.

        A bare substring over a whole page is not an ordering assertion, it
        is a coincidence that has been holding. This reads the cards.
        """
        import re

        body = self.client.get("/board/").content.decode()
        return re.findall(r'<p class="body">(.*?)</p>', body, re.S)

    def assertBefore(self, first, second):
        order = self.feed_order()
        where = [i for i, text in enumerate(order) if first in text]
        other = [i for i, text in enumerate(order) if second in text]
        self.assertTrue(where and other,
                        f"not both on the feed: {first!r}, {second!r} in {order}")
        self.assertLess(where[0], other[0], f"{first!r} should precede {second!r}")

    def test_soonest_first(self):
        far = self.need("fence sometime", needed_by=date.today() + timedelta(days=30))
        soon = self.need("ride thursday", needed_by=date.today() + timedelta(days=2))
        self.sign_in(self.ada_user)

        self.assertBefore("ride thursday", "fence sometime")
        self.assertTrue(soon.needed_by < far.needed_by)

    def test_undated_needs_sit_below_dated_ones_however_new_they_are(self):
        self.need("dated need", needed_by=date.today() + timedelta(days=14))
        self.need("undated need")  # created later, so newer
        self.sign_in(self.ada_user)

        self.assertBefore("dated need", "undated need")

    def test_ordering_ignores_how_much_the_asker_has_given(self):
        """Kit has given 40 hours, Ada none. Kit's need is older and undated;
        Ada's is dated and urgent. Ada's must still come first."""
        from site_app.services import record_contribution

        with tenant_context(self.alpha):
            work = Posting.objects.create(
                organization=self.alpha, member=self.ada, kind=Posting.OFFER,
                description="Somewhere to put hours.")
            for _ in range(5):
                record_contribution(posting=work, member=self.kit,
                                    hours=Decimal("8.00"), note="")

        self.need("kit asks", member=self.kit)
        self.need("ada asks", member=self.ada, needed_by=date.today())
        self.sign_in(self.ada_user)

        self.assertBefore("ada asks", "kit asks")

    def test_urgency_reads_as_words_not_as_a_date_calculation(self):
        today = date.today()
        cases = {
            None: "whenever",
            today: "today",
            today + timedelta(days=1): "tomorrow",
            today + timedelta(days=4): "in 4 days",
            today + timedelta(days=60): "later",
            today - timedelta(days=1): "overdue",
        }
        for when, word in cases.items():
            self.assertEqual(Posting(needed_by=when).urgency, word, msg=str(when))

    def test_a_date_is_optional_on_the_form(self):
        """Forcing a date would make people invent one, and an invented
        deadline outranks a real one."""
        from site_app.forms import PostingForm

        self.assertFalse(PostingForm().fields["needed_by"].required)


class NoticesAreScopedToThisSite(MatchingBase):
    """A dugnadsand member is often a svend user under the same address.

    kjerne_platform.notify keys on email alone and spans the federation by
    design. These tests are what stops that design from leaking another
    product's notices into a mutual aid board — and, worse, from this site
    marking them read.
    """

    def setUp(self):
        super().setUp()
        from kjerne_platform import notify
        self.notify = notify
        self.ours = notify.send("ada@example.test", "dugnadsand", "posting",
                                "Someone here needs a hand.", link="/board/")
        self.theirs = notify.send("ada@example.test", "kjerne-services", "invoice",
                                  "Invoice 41 is overdue.", link="/invoices/41/")

    def tearDown(self):
        # The platform DB is outside Django's test transaction, so these rows
        # survive the rollback that cleans up everything else.
        self.notify.mark_read("ada@example.test", ids=[self.ours, self.theirs])
        with self.notify.get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM notification WHERE id = ANY(%s)",
                        ([self.ours, self.theirs],))
            conn.commit()

    def test_the_page_shows_only_this_sites_notices(self):
        self.sign_in(self.ada_user)
        body = self.client.get("/notices/").content.decode()
        self.assertIn("needs a hand", body)
        self.assertNotIn("Invoice 41", body)

    def test_reading_here_does_not_clear_another_sites_notice(self):
        self.sign_in(self.ada_user)
        self.client.get("/notices/")

        rows = {n["id"]: n for n in self.notify.recent("ada@example.test", limit=20)}
        self.assertIsNotNone(rows[self.ours]["read_at"], "ours should be read")
        self.assertIsNone(rows[self.theirs]["read_at"],
                          "kjerne-services notice was cleared from dugnadsand")

    def test_the_badge_counts_only_this_site(self):
        from site_app.notifications import unread_here

        self.assertEqual(unread_here("ada@example.test"), 1)
