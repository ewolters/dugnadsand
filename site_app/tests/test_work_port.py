"""dugnadsand through the shared port.

Two claims are being tested, and only one of them is about convenience.

The convenient one: an adapter can read this site without knowing a thing
about its schema, because the port speaks contract vocabulary.

The load-bearing one: an adapter is OUTSIDE the tenant. Slack is outside, a
webhook is outside, a digest email is outside. Row-level security scopes these
tables to one organization and stops dead at the process boundary, so anything
handed to an adapter has left the organization for good. Under signal-only that
is existence, state and a link — never the free text, never a member's name.

The rest is about what the port refuses to do. Every invariant in this system
lives in the service layer, so a port that could write generically would route
around all of it while the manifest kept reporting green.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from kjerne_platform.work import port

from site_app.models import Claim, Member, Organization, Posting, Project
from site_app.tenancy import tenant_context

from .helpers import SignedIn

WORK_TOML = "work.toml"

SENSITIVE = "Can someone drive my mother to dialysis on Thursday"


class PortBase(SignedIn, TestCase):
    def setUp(self):
        self.port = port.open(WORK_TOML)
        self.alpha = Organization.objects.create(slug="alpha", name="Alpha Mutual Aid")
        self.beta = Organization.objects.create(slug="beta", name="Beta Mutual Aid")

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


class ReadingWithoutKnowingTheSchema(PortBase):
    def test_items_come_back_in_contract_vocabulary(self):
        with tenant_context(self.alpha):
            items = self.port.items()

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.id, self.ride.id)
        self.assertTrue(item.state)          # this site's `open` boolean
        self.assertEqual(item.title, SENSITIVE)   # inside the tenant, full content

    def test_a_filter_is_written_in_contract_terms_not_this_sites_field_names(self):
        """The whole reason an adapter can be written once. `state` is `open`
        here and `status` in hoshined; the adapter says state either way."""
        with tenant_context(self.alpha):
            self.assertEqual(len(self.port.items(state=True)), 1)
            self.assertEqual(len(self.port.items(state=False)), 0)

    def test_asking_for_a_slot_this_site_does_not_map_says_what_it_has(self):
        with tenant_context(self.alpha):
            with self.assertRaises(port.PortError) as caught:
                self.port.items(owner="somebody")
        self.assertIn("maps no item.owner", str(caught.exception))

    def test_the_port_adds_no_scoping_and_relies_on_rls(self):
        """Stated in the port's docstring, so it needs to be true: reading from
        another tenant's context returns nothing because Postgres says so, not
        because the port filtered."""
        with tenant_context(self.beta):
            self.assertEqual(self.port.items(), [])

    def test_containers_read_the_same_way(self):
        with tenant_context(self.alpha):
            Project.objects.create(
                organization=self.alpha, started_by=self.ada,
                name="Repairing homes", description="Roofs and ramps.")
            containers = self.port.containers()
        self.assertEqual([c.name for c in containers], ["Repairing homes"])


class NothingSensitiveCrossesTheBoundary(PortBase):
    """The one that matters. An adapter is not inside the tenant."""

    def test_the_free_text_never_leaves(self):
        with tenant_context(self.alpha):
            payload = self.port.egress(self.port.items()[0])

        flat = " ".join(str(v) for v in payload.values())
        self.assertNotIn("dialysis", flat)
        self.assertNotIn("mother", flat)
        self.assertNotIn(SENSITIVE, flat)

    def test_no_member_name_leaves_either(self):
        with tenant_context(self.alpha):
            payload = self.port.egress(self.port.items()[0])
        self.assertNotIn("Henderson", " ".join(str(v) for v in payload.values()))

    def test_what_does_leave_is_enough_to_be_useful(self):
        """Signal-only is a discipline, not a refusal to function. "Something
        needs a hand — here" does its job."""
        with tenant_context(self.alpha):
            payload = self.port.egress(self.port.items()[0])

        self.assertEqual(payload["id"], self.ride.id)
        self.assertEqual(payload["site"], "dugnadsand")
        self.assertEqual(payload["role"], "item")
        self.assertEqual(payload["link"], "/board/")
        self.assertIn("state", payload)

    def test_signal_only_is_an_allowlist_so_a_new_slot_cannot_leak(self):
        """A denylist would let the next mapped slot out by default. This
        asserts the direction: anything not named is absent."""
        with tenant_context(self.alpha):
            payload = self.port.egress(self.port.items()[0])

        allowed = set(port.SIGNAL_SLOTS) | {"role", "site", "link"}
        self.assertTrue(set(payload) <= allowed, f"leaked: {set(payload) - allowed}")

    def test_the_declared_policy_is_the_strict_one(self):
        self.assertEqual(self.port.egress_policy, port.SIGNAL_ONLY)

    def test_the_digest_adapter_emits_nothing_sensitive(self):
        """End to end through the reference adapter, which is what a Slack
        integration would be a variation of."""
        with tenant_context(self.alpha):
            text = port.digest(self.port)

        self.assertIn("dugnadsand", text)
        self.assertNotIn("dialysis", text)
        self.assertNotIn("Henderson", text)


class TheseVerbsGoThroughTheServiceLayer(PortBase):
    def test_claiming_through_the_port_creates_a_real_claim(self):
        with tenant_context(self.alpha):
            self.port.do("claim", item=self.ride.id, party=self.ola.id)
            self.assertEqual(Claim.objects.filter(posting=self.ride).count(), 1)

    def test_stepping_off_through_the_port_leaves_no_trace(self):
        with tenant_context(self.alpha):
            self.port.do("claim", item=self.ride.id, party=self.ola.id)
            remaining = self.port.do("step-off", item=self.ride.id, party=self.ola.id)

            self.assertEqual(remaining, 0)
            self.assertEqual(Claim.objects.filter(posting=self.ride).count(), 0)

    def test_recording_hours_through_the_port_chains_like_any_other(self):
        from site_app.services import verify_contributions

        with tenant_context(self.alpha):
            self.port.do("record-entry", item=self.ride.id, party=self.ola.id,
                         hours="2.5", note="Drove.")
            self.assertTrue(verify_contributions(self.alpha))

    def test_closing_still_enforces_who_may(self):
        """Proof the verb is a seam and not a bypass: the site's own rule is
        still the thing that decides."""
        with tenant_context(self.alpha):
            with self.assertRaises(PermissionError):
                self.port.do("close-item", item=self.ride.id, party=self.ola.id)
            self.ride.refresh_from_db()
        self.assertTrue(self.ride.open)


class WhatThePortWillNotDo(PortBase):
    def test_an_unbound_verb_raises_rather_than_writing_generically(self):
        with self.assertRaises(port.VerbNotBound):
            self.port.do("assign", item=self.ride.id, party=self.ola.id)

    def test_the_refusal_names_what_is_available(self):
        """Someone will hit this from an adapter with no access to this repo."""
        with self.assertRaises(port.VerbNotBound) as caught:
            self.port.do("assign", item=self.ride.id, party=self.ola.id)
        message = str(caught.exception)
        self.assertIn("claim", message)
        self.assertIn("step-off", message)

    def test_this_site_binds_no_verb_its_own_rules_forbid(self):
        """assign would put somebody on something by somebody else's decision;
        complete would record a duty that was owed. Neither is bound, and the
        absence is the design rather than a gap to fill in later."""
        verbs = set(self.port.verbs())
        for forbidden in ("assign", "complete", "approve", "prioritise",
                          "rank", "settle", "transfer"):
            self.assertNotIn(forbidden, verbs)

    def test_the_port_exposes_no_generic_write(self):
        """The refusal has to be structural. If a create/save/delete ever
        appears on Port, every guarantee above becomes advisory."""
        for banned in ("create", "save", "delete", "update", "write", "insert"):
            self.assertFalse(hasattr(self.port, banned),
                             f"Port grew a generic {banned}()")
