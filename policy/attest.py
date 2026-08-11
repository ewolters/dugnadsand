"""Run the manifest and record the result as a hash-chained attestation.

An attestation states one thing: at this moment, these checks ran and this is
what they returned. It is engineering evidence, not a legal claim, and the
wording throughout is deliberately narrow about that.

Three outcomes:

    UPHELD      every claim was tested and holds
    INCOMPLETE  no claim was breached, but some could not be tested
    BREACHED    at least one claim was tested and does not hold

INCOMPLETE is not a soft pass. The manifest cannot be reported as upheld while
any check is unenforceable, because the most likely reason a check cannot run is
that the thing it protects has not been built — which is exactly when a green
light would be most misleading.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

try:  # tomllib landed in 3.11; this box runs 3.10.
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

from kjerne_platform import chain

from .checks import BREACHED, CHECKS, NOT_ENFORCEABLE, UPHELD

MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.toml"

STATUS_UPHELD = "UPHELD"
STATUS_INCOMPLETE = "INCOMPLETE"
STATUS_BREACHED = "BREACHED"

# Repeated into every stored attestation so the disclaimer travels with the
# record and cannot be separated from it by whoever reads the JSON later.
# An arbitrary but fixed key for pg_advisory_xact_lock. Only this chain uses
# it; the number means nothing beyond "not the same as anybody else's".
_CHAIN_LOCK = 8_231_104

DISCLAIMER = (
    "Engineering manifest, not a legal attestation. This records that automated "
    "checks ran against this codebase and what they returned. It makes no claim "
    "about lawfulness, tax treatment, or the view of any authority, and it has "
    "not been reviewed by counsel."
)


def load_manifest():
    with MANIFEST_PATH.open("rb") as fh:
        return tomllib.load(fh)


def manifest_hash():
    """Hash of the manifest file itself, so an attestation names the version of
    the claims it tested. Editing a claim changes this, which makes an old
    attestation visibly about older wording."""
    return hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest()


def run_checks():
    """Execute every check named in the manifest. Returns (results, status)."""
    manifest = load_manifest()
    results = []

    for inv in manifest["invariant"]:
        fn = CHECKS.get(inv["check"])
        if fn is None:
            # A claim with no implementation is a claim with no backing.
            results.append({
                "id": inv["id"],
                "status": BREACHED,
                "detail": f"Manifest names check '{inv['check']}' but it is not implemented.",
                "evidence": [],
                "claim": inv["claim"],
            })
            continue
        r = fn()
        results.append({
            "id": r.id,
            "status": r.status,
            "detail": r.detail,
            "evidence": r.evidence,
            "claim": inv["claim"],
        })

    if any(r["status"] == BREACHED for r in results):
        status = STATUS_BREACHED
    elif any(r["status"] == NOT_ENFORCEABLE for r in results):
        status = STATUS_INCOMPLETE
    else:
        status = STATUS_UPHELD

    return results, status


def attest(*, persist=True):
    """Run the manifest and, by default, append the result to the chain.

    Returns the attestation payload. Pass persist=False for a dry run — used by
    the test suite and by the on-demand endpoint when it only needs to show
    what a run would say right now.
    """
    results, status = run_checks()
    recorded_at = datetime.now(timezone.utc)

    payload = {
        "subject": "dugnadsand",
        "kind": "engineering-manifest",
        "legal_effect": "none",
        "disclaimer": DISCLAIMER,
        "manifest_version": load_manifest()["manifest"]["version"],
        "manifest_hash": manifest_hash(),
        "status": status,
        "counts": {
            UPHELD: sum(1 for r in results if r["status"] == UPHELD),
            NOT_ENFORCEABLE: sum(1 for r in results if r["status"] == NOT_ENFORCEABLE),
            BREACHED: sum(1 for r in results if r["status"] == BREACHED),
        },
        "results": results,
    }

    if not persist:
        payload["persisted"] = False
        return payload

    # Imported here so run_checks() stays usable without the app registry.
    from django.db import connection, transaction

    from site_app.models import Attestation

    # Same race as the contribution chain: read the tip, add one, insert. Two
    # runs at once — the nightly schedule and somebody triggering it by hand —
    # would compute the same sequence, and one would lose to the unique
    # constraint. This chain has no parent row to lock, so an advisory lock
    # stands in for one. It is released when the transaction ends, whether that
    # is a commit or a crash.
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", [_CHAIN_LOCK])

        previous = Attestation.objects.order_by("-sequence").first()
        sequence = (previous.sequence + 1) if previous else 0
        previous_hash = previous.entry_hash if previous else ""

        entry_hash = chain.entry_hash(
            sequence=sequence,
            recorded_at=recorded_at,
            payload=payload,
            previous_hash=previous_hash,
        )

        # Inside the lock, so the read of the tip and the write of the next
        # link cannot be separated by another run.
        Attestation.objects.create(
            sequence=sequence,
            recorded_at=recorded_at,
            status=status,
            manifest_hash=payload["manifest_hash"],
            payload=payload,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
        )

    payload["persisted"] = True
    payload["sequence"] = sequence
    payload["entry_hash"] = entry_hash
    return payload


def verify():
    """Walk the stored chain. Returns the ChainReport from kjerne_platform."""
    from site_app.models import Attestation

    entries = [
        {
            "sequence": a.sequence,
            "recorded_at": a.recorded_at,
            "payload": a.payload,
            "previous_hash": a.previous_hash,
            "entry_hash": a.entry_hash,
        }
        for a in Attestation.objects.order_by("sequence")
    ]
    tip = entries[-1]["entry_hash"] if entries else None
    return chain.verify_chain(entries, expected_tip=tip)


if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(attest(persist=False), indent=2, default=str))
