"""Where a form says to go afterwards, and who is allowed to say it.

Four member routes take a `back` field from the POST and return the person to
it, so the page they were reading does not jump. The field arrives from the
browser, which means an attacker can put anything in it — and a redirect that
accepts anything is a way to borrow this site's name for somewhere else's
landing page. The rule is that `back` may only ever name a place on this site.

Logout is here for a related reason: a logout that answers GET can be fired by
an image tag on any page anywhere, which signs people out of a site they were
reading. It has always been posted from a form; nothing enforced that.
"""

from django.contrib.auth.models import User
from django.test import TestCase

from site_app.models import Member, Organization
from site_app.tenancy import tenant_context

from .helpers import SignedIn


class LogoutRefusesGet(SignedIn, TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "ada", email="ada@example.test", password="dugnad-test-pw")

    def test_get_logout_is_refused(self):
        self.sign_in(self.user)
        self.assertEqual(self.client.get("/logout/").status_code, 405)

    def test_post_logout_still_signs_out(self):
        self.sign_in(self.user)
        response = self.client.post("/logout/")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(response.wsgi_request.user.is_authenticated)


class BackFieldStaysOnThisSite(SignedIn, TestCase):
    """`thanks` stands in for all four: they share one line of code."""

    def setUp(self):
        self.org = Organization.objects.create(
            slug="alpha", name="Alpha Mutual Aid")
        self.user = User.objects.create_user(
            "ada", email="ada@example.test", password="dugnad-test-pw")
        with tenant_context(self.org):
            self.member = Member.objects.create(
                organization=self.org, user=self.user, display_name="Ada")
        self.sign_in(self.user)

    def _thanks(self, back):
        return self.client.post(
            f"/thanks/{self.member.id}/", {"back": back})

    def test_a_path_on_this_site_is_honoured(self):
        self.assertEqual(self._thanks("/days/")["Location"], "/days/")

    def test_an_absolute_url_elsewhere_is_refused(self):
        self.assertEqual(
            self._thanks("https://evil.example/harvest/")["Location"], "/board/")

    def test_a_scheme_relative_url_elsewhere_is_refused(self):
        self.assertEqual(
            self._thanks("//evil.example/harvest/")["Location"], "/board/")

    def test_a_missing_back_falls_back_to_the_board(self):
        self.assertEqual(self._thanks("")["Location"], "/board/")
