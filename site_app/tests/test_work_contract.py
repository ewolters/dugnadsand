"""dugnadsand against the shared work contract.

The contract lives in kjerne_platform/work/spec.toml and covers seven
incompatible ideas of "a project" across this estate. This site is the pole
that declares almost nothing, which makes it the useful one to keep honest: if
somebody adds `owner` to Posting, or `completed_at`, or a rate, the undeclared
check fails here before anyone has to spot it in review.

It overlaps the policy manifest on purpose and is not redundant with it. The
manifest checks THIS site against its own promises. The contract checks it
against a vocabulary shared with sites that promise the opposite — so a field
this site's manifest happens not to name is still caught, as long as any other
implementation in the estate gave that meaning a name.
"""

from pathlib import Path

from django.test import SimpleTestCase

from kjerne_platform.work import conformance

WORK_TOML = Path(__file__).resolve().parents[2] / "work.toml"


class ConformsToTheWorkContract(SimpleTestCase):
    def test_the_site_is_conformant(self):
        report = conformance.check(WORK_TOML)
        self.assertTrue(report.ok, f"\n{report}")

    def test_it_declares_only_scheduling(self):
        """Every other extension in the spec makes a claim about a person.
        A date is a fact about the work, which is why it is the only one this
        site can carry."""
        dialect = conformance.load_dialect(WORK_TOML)
        self.assertEqual(dialect["extensions"], ["scheduling"])

    def test_the_invariants_it_declares_match_the_manifest(self):
        """The dialect names this site's invariants so the contract can prove
        no declared extension contradicts one. If the manifest grows a claim
        and the dialect does not, the contract is checking against a promise
        that is no longer complete — and it would still report green, which is
        the worst kind of wrong."""
        from policy.attest import load_manifest

        manifest = {i["id"] for i in load_manifest()["invariant"]}
        declared = set(conformance.load_dialect(WORK_TOML)["invariants"])
        self.assertEqual(declared, manifest)
