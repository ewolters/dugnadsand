"""Single-use setup links.

The point of a link over a printed password is that nothing which works travels
by email. These tests hold the three properties that make that true: the token
is not stored, the link dies when used, and it dies on its own after a week.
"""

from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from site_app.models import Member, Organization, SetupLink
from site_app.services_members import create_member
from site_app.services_setup import (LinkUnusable, issue_setup_link,
                                     resolve_setup_link)
from site_app.tenancy import bypass_rls, set_tenant, tenant_context

from .helpers import SignedIn


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
    def test_a_dry_run_sends_nothing_and_prints_no_url(self):
        """This test used to require the URL, which required minting it.

        It checked the one thing that was fine — no mail went out — and then
        pinned the defect as the contract, because a dry run cannot print a
        link without creating one. Removing the bug broke this test, which is
        how a test can hold a bug in place more firmly than no test would.
        """
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        with mock.patch("kjerne_platform.email.send") as send:
            call_command("send_setup_link", "ada", dry_run=True, stdout=out)
        send.assert_not_called()
        self.assertNotIn("/setup/", out.getvalue())

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


class ADryRunMintsNothing(SignedIn, TestCase):
    """A rehearsal that leaves a working credential behind is not a rehearsal.

    The first version called issue_setup_link() and THEN checked the flag, so
    --dry-run persisted a live single-use link and printed it to a terminal.
    It went unnoticed because the command's output looked exactly like what
    somebody running a dry run wanted to see.
    """

    def setUp(self):
        self.org = Organization.objects.create(slug="alpha", name="Alpha")
        self.user = User.objects.create_user(
            "ada", email="ada@example.test", password="dugnad-test-pw")
        with tenant_context(self.org):
            self.member = Member.objects.create(
                organization=self.org, display_name="Ada", user=self.user)

    def run_command(self, *args):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("send_setup_link", "ada", *args, stdout=out)
        return out.getvalue()

    def links(self):
        from site_app.models import SetupLink
        from site_app.tenancy import bypass_rls

        with bypass_rls():
            return SetupLink.objects.count()

    def test_a_dry_run_creates_no_link(self):
        before = self.links()
        self.run_command("--dry-run")
        self.assertEqual(self.links(), before)

    def test_a_dry_run_prints_no_url(self):
        """It cannot print one honestly: there is no URL until a link exists,
        and printing one would mean having minted it."""
        output = self.run_command("--dry-run")
        self.assertNotIn("/setup/", output)

    def test_a_dry_run_still_says_who_it_would_reach(self):
        """Otherwise it checks nothing worth checking."""
        output = self.run_command("--dry-run")
        self.assertIn("ada@example.test", output)
        self.assertIn("Alpha", output)

    def test_a_dry_run_still_refuses_what_a_real_run_would(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        self.user.email = ""
        self.user.save(update_fields=["email"])
        with self.assertRaises(CommandError):
            call_command("send_setup_link", "ada", "--dry-run")

    def test_a_real_run_does_create_one(self):
        from unittest.mock import patch

        before = self.links()
        with patch("kjerne_platform.email.send", return_value=1):
            output = self.run_command()

        self.assertEqual(self.links(), before + 1)
        self.assertIn("sent", output.lower())

    def test_the_mail_does_not_repeat_the_stale_one_record_claim(self):
        """The same sentence the front page carried after material shipped.
        This one goes to a person's inbox, where nothing renders it visible to
        anybody who might notice."""
        from unittest.mock import patch

        with patch("kjerne_platform.email.send", return_value=1) as send:
            self.run_command()

        body = send.call_args.kwargs["body"].lower()
        self.assertNotIn("one record", body)
        self.assertIn("never what it was worth", body)
