"""Asking somebody who has no account, and the one setting that inverts it.

kjerne's version of this records a decline and tells the requester, correctly:
somebody planned around that person and needs to replan. Here a recorded
refusal is the obligation the whole system exists to remove. Same mechanism,
opposite policy, two lines of TOML — which is the only version of this that
survives a third site.

The tests below are mostly about what does NOT happen when somebody says no.
"""

from django.contrib.auth.models import User
from django.test import TestCase

from kjerne_platform.work import port as work_port
from kjerne_platform.work import tokens

from site_app.models import Claim, Member, Organization, Posting
from site_app.tenancy import tenant_context

from .helpers import SignedIn

WORK_TOML = "work.toml"
SENSITIVE = "Can someone drive my mother to dialysis on Thursday"


class DualPathBase(SignedIn, TestCase):
    def setUp(self):
        self.port = work_port.open(WORK_TOML)
        self.alpha = Organization.objects.create(slug="alpha", name="Alpha Mutual Aid")
        self.ada_user = User.objects.create_user(
            "ada", email="ada@example.test", password="dugnad-test-pw")
        self.ola_user = User.objects.create_user(
            "ola", email="ola@example.test", password="dugnad-test-pw")

        with tenant_context(self.alpha):
            self.ada = Member.objects.create(
                organization=self.alpha, display_name="Ada Henderson",
                user=self.ada_user)
            self.ola = Member.objects.create(
                organization=self.alpha, display_name="Ola", user=self.ola_user)
            self.ride = Posting.objects.create(
                organization=self.alpha, member=self.ada, kind=Posting.NEED,
                description=SENSITIVE)

        self.minted = []

    def tearDown(self):
        """Tokens live in the shared platform DB, outside Django's rollback."""
        if not self.minted:
            return
        from kjerne_platform.db import get_conn
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM work_action_token WHERE token = ANY(%s)",
                        (self.minted,))
            conn.commit()

    def mint(self, side=tokens.CONFIRM, verb="claim"):
        token = tokens.issue(
            self.port, verb=verb, recipient="neighbour@example.test", side=side,
            tenant=self.alpha.id,
            payload={"item": str(self.ride.id), "party": str(self.ola.id)})
        self.minted.append(token)
        return token


class SayingYes(DualPathBase):
    def test_a_confirm_link_claims_through_the_sites_service_layer(self):
        token = self.mint()
        with tenant_context(self.alpha):
            side, _ = tokens.redeem(self.port, token)
            self.assertEqual(side, tokens.CONFIRM)
            self.assertEqual(Claim.objects.filter(posting=self.ride).count(), 1)

    def test_the_same_link_cannot_be_spent_twice(self):
        """A mail forwards. Two clicks must not mean two people believing they
        are the one on it — which is why the claim and the marking are a single
        UPDATE rather than a read, a check and a write."""
        token = self.mint()
        with tenant_context(self.alpha):
            tokens.redeem(self.port, token)
            with self.assertRaises(tokens.TokenRefused):
                tokens.redeem(self.port, token)
            self.assertEqual(Claim.objects.filter(posting=self.ride).count(), 1)


class SayingNo(DualPathBase):
    """The setting that makes this site different from kjerne."""

    def test_declining_records_nothing_at_all(self):
        token = self.mint(side=tokens.DECLINE)
        with tenant_context(self.alpha):
            side, result = tokens.redeem(self.port, token)

            self.assertEqual(side, tokens.DECLINE)
            self.assertIsNone(result)
            self.assertEqual(Claim.objects.filter(posting=self.ride).count(), 0)

    def test_declining_leaves_the_system_where_ignoring_would_have(self):
        """The real claim. Saying no and never opening the mail must be
        indistinguishable in every table this site owns."""
        with tenant_context(self.alpha):
            before = (Claim.objects.count(), Posting.objects.filter(open=True).count())

        token = self.mint(side=tokens.DECLINE)
        with tenant_context(self.alpha):
            tokens.redeem(self.port, token)
            after = (Claim.objects.count(), Posting.objects.filter(open=True).count())

        self.assertEqual(before, after)

    def test_nobody_is_notified_that_somebody_declined(self):
        from unittest.mock import patch

        token = self.mint(side=tokens.DECLINE)
        with patch("kjerne_platform.notify.send") as send:
            with tenant_context(self.alpha):
                tokens.redeem(self.port, token)
        self.assertEqual(send.call_count, 0)

    def test_the_decline_link_still_works_once_rather_than_404ing(self):
        """If declining 404'd, which button worked would tell the sender what
        the recipient chose. The link has to be real to be silent."""
        token = self.mint(side=tokens.DECLINE)
        with tenant_context(self.alpha):
            side, _ = tokens.redeem(self.port, token)
            self.assertEqual(side, tokens.DECLINE)
            with self.assertRaises(tokens.TokenRefused):
                tokens.redeem(self.port, token)


class WhatATokenMayNotDo(DualPathBase):
    def test_a_verb_the_settings_do_not_permit_cannot_be_minted(self):
        """record-entry would let a forwarded mail write arbitrary hours."""
        with self.assertRaises(ValueError) as caught:
            tokens.issue(self.port, verb="record-entry", payload={},
                         recipient="x@example.test")
        self.assertIn("does not permit", str(caught.exception))

    def test_closing_somebody_elses_posting_cannot_be_minted_either(self):
        with self.assertRaises(ValueError):
            tokens.issue(self.port, verb="close-item", payload={},
                         recipient="x@example.test")

    def test_a_verb_the_site_never_bound_cannot_be_minted(self):
        with self.assertRaises(ValueError):
            tokens.issue(self.port, verb="assign", payload={},
                         recipient="x@example.test")

    def test_the_holder_cannot_change_what_the_link_does(self):
        """The payload is fixed at issue time. Redemption takes a token and
        nothing else, so there is no parameter for a holder to tamper with."""
        import inspect
        params = list(inspect.signature(tokens.redeem).parameters)
        self.assertEqual(params, ["port", "token"])


class EveryRefusalLooksTheSame(DualPathBase):
    """"That link has expired" tells a stranger a link once existed."""

    def test_an_unknown_token_and_a_spent_one_are_indistinguishable(self):
        spent = self.mint()
        with tenant_context(self.alpha):
            tokens.redeem(self.port, spent)

            messages = set()
            for candidate in (spent, "never-existed", "", "x" * 200):
                try:
                    tokens.redeem(self.port, candidate)
                except tokens.TokenRefused as exc:
                    messages.add(str(exc))
        self.assertEqual(messages, {tokens.REFUSED})

    def test_the_page_says_the_same_thing_however_it_failed(self):
        spent = self.mint()
        with tenant_context(self.alpha):
            tokens.redeem(self.port, spent)

        spent_body = self.client.get(f"/act/{spent}/").content.decode()
        unknown_body = self.client.get("/act/never-existed/").content.decode()
        self.assertEqual(spent_body, unknown_body)

    def test_a_refused_link_is_a_404(self):
        self.assertEqual(self.client.get("/act/nope/").status_code, 404)


class TheEndpointNeedsNoAccount(DualPathBase):
    def test_a_signed_out_visitor_can_spend_a_confirm_link(self):
        """The whole point. If this required a login the feature would be for
        people who already have one."""
        token = self.mint()
        response = self.client.get(f"/act/{token}/")

        self.assertEqual(response.status_code, 200)
        with tenant_context(self.alpha):
            self.assertEqual(Claim.objects.filter(posting=self.ride).count(), 1)

    def test_the_page_carries_nothing_about_the_posting(self):
        """Whoever holds this link is outside the tenant until they sign in.
        Signal-only applies to the page they land on too."""
        token = self.mint()
        body = self.client.get(f"/act/{token}/").content.decode()

        self.assertNotIn("dialysis", body)
        self.assertNotIn("Henderson", body)


class TheInvitationItself(DualPathBase):
    def test_the_mail_names_neither_the_need_nor_the_person(self):
        from unittest.mock import patch

        from site_app.work_actions import invite

        with patch("kjerne_platform.email.send") as send:
            with tenant_context(self.alpha):
                invite(posting=self.ride, email="neighbour@example.test",
                       member=self.ola)

        body = " ".join(str(v) for v in send.call_args.kwargs.values())
        self.assertNotIn("dialysis", body)
        self.assertNotIn("Henderson", body)
        self.assertIn("/act/", body)

    def test_inviting_returns_nothing_so_no_caller_can_show_reach(self):
        """A count of who was reached is a delivery receipt, and a delivery
        receipt is the first half of knowing somebody said no."""
        from unittest.mock import patch

        from site_app.work_actions import invite

        with patch("kjerne_platform.email.send"):
            with tenant_context(self.alpha):
                self.assertIsNone(
                    invite(posting=self.ride, email="n@example.test",
                           member=self.ola))
