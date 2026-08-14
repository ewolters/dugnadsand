"""Posting without leaving the feed.

Saying "I need a ride on Thursday" cost a page load, a separate screen and a
trip back. Three steps, and the middle one looked like an administrative form
rather than like saying something to people.

The composer now opens in place. What has to hold:

  IT IS ONE PIECE OF MARKUP. It renders on the feed and on its own page, and
  two copies drifted apart within a day the last time a field was added. The
  partial is the single source and a test proves both pages use it.

  AN INVALID POST COMES BACK TO THE FEED. Answering "that date is wrong" by
  moving somebody to a screen they did not ask for, and losing the feed they
  were reading, is the behaviour this replaced. The errors arrive on the feed
  with the composer already open.

  IT WORKS WITHOUT SCRIPT. A <details>, like the account menu. With no CSS it
  is an open form; with no JavaScript it still opens. There is no state
  anywhere but the markup.
"""

import re

from django.test import TestCase

from site_app.models import Posting
from site_app.tenancy import tenant_context

from .test_app import AppBase


class ItIsOnTheFeed(AppBase):
    def test_the_feed_carries_a_working_form(self):
        self.sign_in(self.ada_user)
        body = self.client.get("/board/").content.decode()

        self.assertIn('<details class="compose"', body)
        self.assertIn('action="/board/new/"', body)
        self.assertIn('name="description"', body)
        self.assertIn('name="kind"', body)

    def test_posting_from_the_feed_lands_and_returns_to_the_feed(self):
        self.sign_in(self.ada_user)
        response = self.client.post("/board/new/", {
            "kind": "offer", "description": "A trailer, most Saturdays.",
            "hours_cap": ""})

        self.assertRedirects(response, "/board/")
        with tenant_context(self.alpha):
            self.assertTrue(Posting.objects.filter(
                description="A trailer, most Saturdays.").exists())

    def test_it_starts_closed(self):
        """Open by default would put a form above every read of the feed.
        The pill is the invitation; the box is what it opens."""
        self.sign_in(self.ada_user)
        body = self.client.get("/board/").content.decode()
        self.assertNotIn('<details class="compose" open', body)

    def test_no_script_is_involved(self):
        """A <details>, like the account menu. If this ever needs JavaScript
        it stops working for the people most likely to be on an old phone."""
        self.sign_in(self.ada_user)
        body = self.client.get("/board/").content.decode()
        composer = body[body.index('<details class="compose"'):
                        body.index("</details>")]
        self.assertNotIn("<script", composer)
        self.assertNotIn("onclick", composer)


class AnInvalidPostComesBackToTheFeed(AppBase):
    def bad_post(self):
        return self.client.post("/board/new/", {
            "kind": "offer", "description": "A trailer.",
            "needed_by": "not-a-date"})

    def test_it_does_not_redirect_away(self):
        self.sign_in(self.ada_user)
        self.assertEqual(self.bad_post().status_code, 200)

    def test_the_feed_is_still_there_underneath(self):
        """The whole point. An error must not cost somebody the page they
        were reading."""
        with tenant_context(self.alpha):
            Posting.objects.create(
                organization=self.alpha, member=self.ada, kind=Posting.OFFER,
                description="Something already on the feed.")

        self.sign_in(self.ada_user)
        body = self.bad_post().content.decode()
        self.assertIn("Something already on the feed.", body)

    def test_the_composer_comes_back_open(self):
        """Closed, the person would see an error they had to open a pill to
        find, next to a form that had lost what they typed."""
        self.sign_in(self.ada_user)
        self.assertIn('<details class="compose" open',
                      self.bad_post().content.decode())

    def test_what_was_typed_survives(self):
        self.sign_in(self.ada_user)
        self.assertIn("A trailer.", self.bad_post().content.decode())

    def test_nothing_is_created(self):
        self.sign_in(self.ada_user)
        self.bad_post()
        with tenant_context(self.alpha):
            self.assertFalse(
                Posting.objects.filter(description="A trailer.").exists())


class OneCopyOfTheMarkup(TestCase):
    """Two copies of a form drift apart the next time a field is added."""

    def test_both_pages_include_the_partial(self):
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1] / "templates" / "site_app"
        for name in ("board.html", "posting_form.html"):
            with self.subTest(page=name):
                self.assertIn('include "site_app/_composer.html"',
                              (root / name).read_text())

    def test_the_partial_holds_no_send_row(self):
        """Each page supplies its own: the feed's says Post, the page's
        offers Cancel, and closing a <details> already is the cancel."""
        import pathlib

        partial = (pathlib.Path(__file__).resolve().parents[1] / "templates"
                   / "site_app" / "_composer.html").read_text()
        self.assertNotIn("<button", partial)

    def test_the_standalone_page_still_works(self):
        """Kept as the deep link and as the answer for anybody who lands on
        /board/new/ directly. Removing it would break a bookmark to fix a
        layout."""
        from django.contrib.auth.models import User

        from site_app.models import Member, Organization, Region

        region = Region.objects.create(slug="up", name="Upstate")
        org = Organization.objects.create(slug="a", name="A", region=region)
        user = User.objects.create_user("ada", password="dugnad-test-pw")
        from site_app.tenancy import set_tenant

        set_tenant(org.id, org.region_id)
        Member.objects.create(organization=org, user=user, display_name="Ada")
        set_tenant(None)

        self.client.force_login(user)
        session = self.client.session
        session["mfa_ok"] = True
        session["mfa_verified"] = True
        session.save()

        response = self.client.get("/board/new/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="description"')
