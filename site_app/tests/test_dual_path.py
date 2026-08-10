"""Acting without an account, and the one setting that inverts it.

Retargeted from an invitation flow that could not work. That version emailed a
stranger two links, one of which claimed a posting — but a claim needs a
Member, a stranger is not one, and Member carries no email of its own, so
redemption raised TypeError and the page said "that link is no longer usable".
Pointing somebody at a posting is now a notice to a member, which needs no
capability at all; see services_social.point_at.

What is left is the case the token path was always right for: somebody at a
loading dock signing for goods, whose address comes off the manifest and who
should not need an account to say the pallet arrived.


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

from decimal import Decimal

from django.utils import timezone

from site_app.models import (Manifest, Member, Organization, Posting,
                             StockLine, Warehouse)
from site_app.tenancy import tenant_context

from .helpers import CleansPlatformTokens, SignedIn

WORK_TOML = "work.toml"
SENSITIVE = "Can someone drive my mother to dialysis on Thursday"


class DualPathBase(CleansPlatformTokens, SignedIn, TestCase):
    def setUp(self):
        super().setUp()   # chains into CleansPlatformTokens
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
            self.barn = Warehouse.objects.create(
                organization=self.alpha, holder=self.ada, name="North barn",
                address="Gate 4412")
            self.lumber = StockLine.objects.create(
                organization=self.alpha, warehouse=self.barn,
                description=SENSITIVE, quantity=Decimal("200.00"),
                unit="board-feet", confirmed_at=timezone.now(),
                confirmed_by=self.ada)
            self.doc = Manifest.objects.create(
                organization=self.alpha, stock_line=self.lumber,
                quantity=Decimal("50.00"), destination="Habitat build",
                sent_by=self.ada)


    def mint(self, side=tokens.CONFIRM, verb="confirm-receipt"):
        return tokens.issue(
            self.port, verb=verb, recipient="yard@example.test", side=side,
            tenant=self.alpha.id, payload={"manifest": str(self.doc.id)})


class SayingYes(DualPathBase):
    def test_a_confirm_link_records_receipt_through_the_service_layer(self):
        token = self.mint()
        with tenant_context(self.alpha):
            side, _ = tokens.redeem(self.port, token)
            self.doc.refresh_from_db()
            self.assertEqual(side, tokens.CONFIRM)
            self.assertTrue(self.doc.received)

    def test_the_same_link_cannot_be_spent_twice(self):
        """A QR is photographed and forwarded. Two scans must not both act —
        which is why the claim and the marking are a single UPDATE rather than
        a read, a check and a write."""
        token = self.mint()
        with tenant_context(self.alpha):
            tokens.redeem(self.port, token)
            with self.assertRaises(tokens.TokenRefused):
                tokens.redeem(self.port, token)


class SayingNo(DualPathBase):
    """The setting that makes this site different from kjerne."""

    def test_declining_records_nothing_at_all(self):
        token = self.mint(side=tokens.DECLINE)
        with tenant_context(self.alpha):
            side, result = tokens.redeem(self.port, token)

            self.assertEqual(side, tokens.DECLINE)
            self.assertIsNone(result)
            self.doc.refresh_from_db()
            self.assertFalse(self.doc.received)

    def test_declining_leaves_the_system_where_ignoring_would_have(self):
        """The real claim. Saying no and never opening the mail must be
        indistinguishable in every table this site owns."""
        with tenant_context(self.alpha):
            before = (Manifest.objects.filter(received_at__isnull=False).count(),
                      Posting.objects.filter(open=True).count())

        token = self.mint(side=tokens.DECLINE)
        with tenant_context(self.alpha):
            tokens.redeem(self.port, token)
            after = (Manifest.objects.filter(received_at__isnull=False).count(),
                     Posting.objects.filter(open=True).count())

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
    def test_claiming_is_no_longer_reachable_by_token_at_all(self):
        """It was permitted for an invitation flow that could not work, and a
        verb no code mints is surface for nothing."""
        with self.assertRaises(ValueError):
            tokens.issue(self.port, verb="claim", payload={},
                         recipient="x@example.test")

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
            self.doc.refresh_from_db()
            self.assertTrue(self.doc.received)

    def test_the_page_carries_nothing_about_the_posting(self):
        """Whoever holds this link is outside the tenant until they sign in.
        Signal-only applies to the page they land on too."""
        token = self.mint()
        body = self.client.get(f"/act/{token}/").content.decode()

        self.assertNotIn("dialysis", body)
        self.assertNotIn("Henderson", body)
