"""Single-use setup links.

The point of a link over a printed password is that nothing which works travels
by email. These tests hold the three properties that make that true: the token
is not stored, the link dies when used, and it dies on its own after a week.
"""

from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from site_app.models import Member, Organization, SetupLink
from site_app.services_members import create_member
from site_app.services_setup import (LinkUnusable, issue_setup_link,
                                     resolve_setup_link)
from site_app.tenancy import bypass_rls, set_tenant, tenant_context


class SetupLinkBase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(slug="alpha", name="Alpha Mutual Aid")
        self.member, _ = create_member(
            organization=self.org, username="ada", display_name="Ada",
            email="ada@example.org")
        set_tenant(None)

    def tearDown(self):
        set_tenant(None)


class TokenHandling(SetupLinkBase):
    def test_the_token_itself_is_never_stored(self):
        """A copy of the table must not be a set of working invitations."""
        token = issue_setup_link(self.member)
        with bypass_rls():
            link = SetupLink.objects.get(member=self.member, used_at__isnull=True)
        self.assertNotEqual(link.token_hash, token)
        self.assertNotIn(token, link.token_hash)
        self.assertEqual(len(link.token_hash), 64)

    def test_a_fresh_token_resolves_to_its_member(self):
        token = issue_setup_link(self.member)
        _link, member = resolve_setup_link(token)
        self.assertEqual(member.pk, self.member.pk)

    def test_an_unknown_token_is_refused(self):
        with self.assertRaises(LinkUnusable):
            resolve_setup_link("not-a-real-token")

    def test_an_expired_token_is_refused(self):
        token = issue_setup_link(self.member, lifetime=timedelta(seconds=-1))
        with self.assertRaises(LinkUnusable):
            resolve_setup_link(token)

    def test_issuing_a_second_link_retires_the_first(self):
        # Two invitations must not mean two live ways in.
        first = issue_setup_link(self.member)
        second = issue_setup_link(self.member)

        with self.assertRaises(LinkUnusable):
            resolve_setup_link(first)
        self.assertIsNotNone(resolve_setup_link(second))


class FollowingTheLink(SetupLinkBase):
    def test_it_sets_a_password_and_goes_to_the_second_factor(self):
        token = issue_setup_link(self.member)
        response = self.client.post(f"/setup/{token}/", {
            "new_password1": "a-quiet-saturday-97",
            "new_password2": "a-quiet-saturday-97",
        })
        self.assertRedirects(response, "/mfa/setup/", fetch_redirect_response=False)

        self.member.user.refresh_from_db()
        self.assertTrue(self.member.user.check_password("a-quiet-saturday-97"))

        with tenant_context(self.org):
            self.member.refresh_from_db()
            self.assertFalse(self.member.must_change_password)

    def test_the_link_cannot_be_followed_twice(self):
        token = issue_setup_link(self.member)
        self.client.post(f"/setup/{token}/", {
            "new_password1": "a-quiet-saturday-97",
            "new_password2": "a-quiet-saturday-97"})
        self.client.post("/logout/")

        again = self.client.get(f"/setup/{token}/")
        self.assertEqual(again.status_code, 404)

    def test_a_failed_password_does_not_burn_the_link(self):
        # Mistyping a confirmation should not cost somebody their invitation.
        token = issue_setup_link(self.member)
        self.client.post(f"/setup/{token}/", {
            "new_password1": "one-thing", "new_password2": "another-thing"})
        self.assertEqual(self.client.get(f"/setup/{token}/").status_code, 200)

    def test_every_refusal_is_byte_for_byte_identical(self):
        """Unknown, used and expired must be indistinguishable.

        An earlier version rendered the specific reason, so "has expired" told a
        visitor a token had once been real while "is not valid" told them it
        never was. The reason goes to the log now; the page says one thing.
        """
        token = issue_setup_link(self.member)
        self.client.post(f"/setup/{token}/", {
            "new_password1": "a-quiet-saturday-97",
            "new_password2": "a-quiet-saturday-97"})
        self.client.logout()

        unknown = self.client.get("/setup/nope/")
        used = self.client.get(f"/setup/{token}/")
        expired = self.client.get(
            f"/setup/{issue_setup_link(self.member, lifetime=timedelta(seconds=-1))}/")

        for response in (unknown, used, expired):
            self.assertEqual(response.status_code, 404)
        self.assertEqual(unknown.content, used.content)
        self.assertEqual(unknown.content, expired.content)


class SendCommand(SetupLinkBase):
    def test_a_dry_run_sends_nothing(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        with mock.patch("kjerne_platform.email.send") as send:
            call_command("send_setup_link", "ada", dry_run=True, stdout=out)
        send.assert_not_called()
        self.assertIn("/setup/", out.getvalue())

    def test_it_queues_one_email_to_the_members_address(self):
        from io import StringIO

        from django.core.management import call_command

        with mock.patch("kjerne_platform.email.send", return_value=1) as send:
            call_command("send_setup_link", "ada", stdout=StringIO())
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs["to"], "ada@example.org")
        self.assertEqual(send.call_args.kwargs["site"], "dugnadsand")
        # The body carries a link, never a password.
        self.assertIn("/setup/", send.call_args.kwargs["body"])
        self.assertNotIn("password:", send.call_args.kwargs["body"].lower())

    def test_a_member_without_an_email_is_refused(self):
        from io import StringIO

        from django.core.management import call_command
        from django.core.management.base import CommandError

        self.member.user.email = ""
        self.member.user.save(update_fields=["email"])
        with self.assertRaises(CommandError):
            call_command("send_setup_link", "ada", stdout=StringIO())
