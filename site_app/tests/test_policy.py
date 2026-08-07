"""The manifest is only worth what its enforcement is worth.

These tests do three jobs:

1. Guard the guard — every claim has an implementation and every implementation
   has a claim, so a claim cannot quietly become decorative.
2. Run every check and fail the build on any breach.
3. Refuse the vacuous pass — assert that an unenforceable check can never be
   reported as UPHELD, which is the failure mode a manifest invites.

Nothing here is a legal test. It tests that the software behaves the way the
manifest says it behaves, and nothing further.
"""

from django.test import TestCase

from policy import attest
from policy.checks import BREACHED, CHECKS, NOT_ENFORCEABLE, UPHELD


class ManifestIntegrity(TestCase):
    def setUp(self):
        self.manifest = attest.load_manifest()
        self.invariants = self.manifest["invariant"]

    def test_the_manifest_declares_it_is_not_a_legal_attestation(self):
        # If this ever changes, someone is about to over-claim in a board packet.
        self.assertEqual(self.manifest["manifest"]["legal_effect"], "none")
        self.assertEqual(self.manifest["manifest"]["kind"], "engineering-manifest")

    def test_every_claim_has_an_implementation(self):
        missing = [i["id"] for i in self.invariants if i["check"] not in CHECKS]
        self.assertEqual(missing, [], f"claims with no backing code: {missing}")

    def test_every_implementation_has_a_claim(self):
        # The other direction. A check nobody declared is a check nobody reads.
        declared = {i["check"] for i in self.invariants}
        orphans = sorted(set(CHECKS) - declared)
        self.assertEqual(orphans, [], f"checks absent from the manifest: {orphans}")

    def test_every_claim_states_why_it_exists(self):
        thin = [i["id"] for i in self.invariants if len(i.get("why", "").strip()) < 40]
        self.assertEqual(thin, [], f"claims with no stated rationale: {thin}")


class ChecksRun(TestCase):
    def test_no_claim_is_breached(self):
        results, _ = attest.run_checks()
        breached = [
            f"{r['id']}: {r['detail']} {r['evidence']}"
            for r in results if r["status"] == BREACHED
        ]
        self.assertEqual(breached, [], "policy manifest breached:\n" + "\n".join(breached))

    def test_money_rails_are_enforceable_today_and_hold(self):
        # This one needs no domain models, so it must be genuinely green now.
        # If it ever reports not_enforceable, the check has been weakened.
        result = CHECKS["no_money_rails"]()
        self.assertEqual(result.status, UPHELD, result.detail)

    def test_tax_artifact_check_is_enforceable_today_and_holds(self):
        result = CHECKS["no_tax_artifact"]()
        self.assertEqual(result.status, UPHELD, result.detail)


class NoVacuousPass(TestCase):
    """The manifest must never look green because it tested nothing."""

    def test_status_is_never_upheld_while_a_check_cannot_run(self):
        results, status = attest.run_checks()
        unenforceable = [r["id"] for r in results if r["status"] == NOT_ENFORCEABLE]
        if unenforceable:
            self.assertEqual(
                status, attest.STATUS_INCOMPLETE,
                f"reported {status} while these could not be tested: {unenforceable}",
            )

    def test_attestation_carries_its_own_disclaimer(self):
        # The disclaimer must travel inside the record, so it cannot be
        # separated from the JSON by whoever reads it later.
        payload = attest.attest(persist=False)
        self.assertEqual(payload["legal_effect"], "none")
        self.assertIn("not a legal attestation", payload["disclaimer"])

    def test_attestation_names_the_manifest_version_it_tested(self):
        payload = attest.attest(persist=False)
        self.assertEqual(len(payload["manifest_hash"]), 64)


class ChainIntegrity(TestCase):
    def test_attestations_chain_and_verify(self):
        first = attest.attest()
        second = attest.attest()

        self.assertEqual(first["sequence"], 0)
        self.assertEqual(second["sequence"], 1)

        report = attest.verify()
        self.assertTrue(report.ok, getattr(report, "problems", report))

    def test_rewriting_an_attestation_breaks_the_chain(self):
        attest.attest()
        attest.attest()

        from site_app.models import Attestation
        first = Attestation.objects.order_by("sequence").first()
        payload = dict(first.payload)
        payload["status"] = "UPHELD"          # the lie an operator would tell
        Attestation.objects.filter(pk=first.pk).update(payload=payload)

        report = attest.verify()
        self.assertFalse(report.ok, "a rewritten attestation verified clean")


# --------------------------------------------------------------------------
# The runtime half of no-gating. Static analysis in policy/checks.py cannot see
# through indirection, so the claim is also tested by driving a real claim and
# watching the SQL. Skipped until the domain models exist — and the manifest
# reports INCOMPLETE for exactly as long as that is true, so the gap is visible
# rather than assumed away.
# --------------------------------------------------------------------------

class NoGatingAtRuntime(TestCase):
    def test_claiming_never_reads_the_contribution_ledger(self):
        try:
            from site_app.models import Claim, Contribution, Offering  # noqa: F401
        except ImportError:
            self.skipTest("domain models not built yet; manifest reports INCOMPLETE")

        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        offering = Offering.objects.first()
        with CaptureQueriesContext(connection) as ctx:
            self.client.post(f"/offerings/{offering.id}/claim/")

        touched = " ".join(q["sql"].lower() for q in ctx.captured_queries)
        self.assertNotIn(
            "contribution", touched,
            "The claim path read the contribution ledger. Nothing may gate on what a "
            "member has given — see docs/design-rules.md §1.",
        )
