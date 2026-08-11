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

from .helpers import SignedIn

from policy import attest
from policy.checks import BREACHED, CHECKS, NOT_ENFORCEABLE, UPHELD


class ManifestIntegrity(SignedIn, TestCase):
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


class ChecksRun(SignedIn, TestCase):
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


class NoVacuousPass(SignedIn, TestCase):
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


class ChainIntegrity(SignedIn, TestCase):
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
        # Use a sentinel rather than a real status. The first version of this
        # test wrote "UPHELD", which silently became a no-op the day the real
        # status turned UPHELD — so it passed by coincidence of the value it
        # picked rather than by detecting anything.
        payload = dict(first.payload)
        self.assertNotEqual(payload.get("status"), "TAMPERED-BY-TEST")
        payload["status"] = "TAMPERED-BY-TEST"
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

class NoGatingAtRuntime(SignedIn, TestCase):
    """The runtime half of no-gating.

    Static analysis cannot see through indirection, so the claim is also tested
    by driving a real claim and watching the SQL. The test asserts the claim
    actually SUCCEEDED before asserting nothing was read — otherwise a redirect
    to a login page would satisfy it trivially, which is the vacuous pass this
    whole manifest exists to avoid.
    """

    def setUp(self):
        from django.contrib.auth.models import User

        from site_app.models import Member, Posting, Organization
        from site_app.tenancy import set_tenant, tenant_context

        self.org = Organization.objects.create(slug="probe", name="Probe Mutual Aid")
        self.user = User.objects.create_user("probe", password="dugnad-test-pw")
        with tenant_context(self.org):
            self.member = Member.objects.create(
                organization=self.org, display_name="Probe", user=self.user)
            self.posting = Posting.objects.create(
                organization=self.org, member=self.member,
                description="A spare afternoon.")
        set_tenant(None)

    def test_claiming_never_reads_the_contribution_ledger(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from site_app.models import Claim
        from site_app.tenancy import tenant_context

        self.sign_in(self.user)

        with CaptureQueriesContext(connection) as ctx:
            response = self.client.post(f"/board/{self.posting.id}/claim/")

        # Guard the guard: prove the claim path actually ran.
        self.assertEqual(response.status_code, 302, "the claim did not succeed")
        with tenant_context(self.org):
            self.assertEqual(Claim.objects.count(), 1, "no claim was created")

        touched = " ".join(q["sql"].lower() for q in ctx.captured_queries)
        self.assertIn("site_app_claim", touched, "no claim SQL was captured")
        self.assertNotIn(
            "site_app_contribution", touched,
            "The claim path read the contribution ledger. Nothing may gate on what a "
            "member has given - see docs/design-rules.md section 1.",
        )


class RoutingNeverConsultsTheRecord(SignedIn, TestCase):
    """no-routing-by-record, and proof that it can fail.

    The check's own subject is a file list, so a typo in DELIVERY_MODULES would
    make it pass by scanning nothing. These tests pin both directions.
    """

    def test_the_delivery_modules_it_claims_to_scan_actually_exist(self):
        from pathlib import Path

        from policy.checks import BASE_DIR, DELIVERY_MODULES

        self.assertTrue(DELIVERY_MODULES)
        for name in DELIVERY_MODULES:
            self.assertTrue(Path(BASE_DIR / name).exists(),
                            f"{name} is listed as a delivery path but is not there")

    def test_it_holds_today(self):
        from policy.checks import UPHELD, no_routing_by_record

        self.assertEqual(no_routing_by_record().status, UPHELD)

    def test_it_breaks_when_a_delivery_path_names_the_ledger(self):
        """The feature it forbids: recipients ranked by what they have given."""
        from unittest.mock import patch

        from policy import checks

        source = "def _audience(org):\n    from .models import Contribution\n"
        with patch.object(checks.Path, "read_text", lambda self: source), \
             patch.object(checks.Path, "exists", lambda self: True):
            result = checks.no_routing_by_record()

        self.assertEqual(result.status, checks.BREACHED)
        self.assertTrue(any("Contribution" in e for e in result.evidence))

    def test_it_reports_unenforceable_rather_than_passing_when_nothing_is_there(self):
        from unittest.mock import patch

        from policy import checks

        with patch.object(checks.Path, "exists", lambda self: False):
            result = checks.no_routing_by_record()
        self.assertEqual(result.status, checks.NOT_ENFORCEABLE)


class TheStatementMatchesTheManifest(SignedIn, TestCase):
    """A policy statement is worth exactly as much as its accuracy.

    docs/policy-statement.md restates the commitments in prose for somebody
    deciding whether their organization should use this. Prose drifts: an
    invariant gets added and the statement does not mention it, or the
    statement keeps describing one that was renamed. Either way it becomes a
    document that says more than the code does — which is the failure the copy
    sweep already found on three pages.

    So the check runs both directions.
    """

    @staticmethod
    def statement():
        from pathlib import Path

        return (Path(__file__).resolve().parents[2]
                / "docs" / "policy-statement.md").read_text()

    @staticmethod
    def manifest():
        from policy.attest import load_manifest

        return load_manifest()

    def test_every_commitment_in_the_manifest_appears_in_the_statement(self):
        """A commitment the code enforces but the statement omits is one
        somebody was never told they had."""
        text = self.statement()
        missing = [i["id"] for i in self.manifest()["invariant"]
                   if i["id"] not in text]
        self.assertEqual(missing, [], f"not in the statement: {missing}")

    def test_every_commitment_named_in_the_statement_is_really_enforced(self):
        """The dangerous direction: a promise in prose with nothing behind
        it."""
        import re

        declared = {i["id"] for i in self.manifest()["invariant"]}
        named = set(re.findall(r"`(no-[a-z-]+|flat-hours)`", self.statement()))

        self.assertTrue(named)
        self.assertTrue(named <= declared, f"claimed but not enforced: {named - declared}")

    def test_it_quotes_the_manifest_wording_rather_than_paraphrasing(self):
        """A paraphrase is where a claim quietly grows. The table is the
        operative wording, verbatim."""
        text = self.statement()
        for invariant in self.manifest()["invariant"]:
            self.assertIn(invariant["claim"], text, invariant["id"])

    def test_it_says_which_document_wins(self):
        text = self.statement().lower()
        self.assertIn("the manifest is correct and this document is stale", text)

    def test_it_refuses_to_be_read_as_legal_advice(self):
        text = self.statement().lower()
        for required in ("not legal advice", "not a legal attestation",
                         "your own counsel"):
            self.assertIn(required, text, required)

    def test_it_states_what_is_not_promised(self):
        """The section that stops it being marketing."""
        text = self.statement().lower()
        self.assertIn("deliberately not promised", text)
        # The specific overclaim the copy sweep caught, named here so it
        # cannot creep back in through this document.
        self.assertIn("individual contributions are visible", text)
