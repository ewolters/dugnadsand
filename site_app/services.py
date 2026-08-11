"""Domain operations.

Two rules govern everything here, and both are checked by policy/manifest.toml:

1. Claiming never consults what the claimant has given. There is no lookup to
   forget to remove — `claim_posting` does not import Contribution at all.
2. Nothing links a claim to a contribution. Recording hours and taking an
   posting are separate acts that never meet in a row.
"""

from datetime import datetime, timezone
from decimal import Decimal

from django.db import transaction
from kjerne_platform import chain

from .models import Claim, Contribution, Organization

# Contribution.hours is decimal_places=2, so Decimal("3.5") comes back out of
# Postgres as Decimal("3.50"). Hashing str(hours) on the way in and on the way
# out therefore produced two different strings for the same value, and an
# untampered chain failed to verify. Canonicalise on both sides.
HOURS_QUANT = Decimal("0.01")


def _canonical_hours(hours):
    return str(Decimal(hours).quantize(HOURS_QUANT))


def claim_posting(*, posting, member):
    """Take what was offered.

    Deliberately absent: any check on the claimant's history, any decrement, any
    settlement. Everyone may claim, including someone who has never given
    anything and never will. That is the point of the whole system, and the
    reason this function is four lines.
    """
    if not posting.open:
        raise ValueError("That posting is closed.")
    if posting.organization_id != member.organization_id:
        raise ValueError("Posting and member belong to different organizations.")

    return Claim.objects.create(
        organization_id=member.organization_id,
        posting=posting,
        member=member,
    )


def step_off(*, posting, member):
    """Stop being the one on this. Returns how many people are still on it.

    A HARD DELETE, and that is the whole design. The obvious implementation is
    a `withdrawn` flag or a `stepped_off_at` timestamp, because keeping history
    is normally the responsible choice. Here it is the harmful one: a stored
    record of stepping off is a record of not following through, and once that
    exists somebody can count it. "Ada has stepped off four times" is a
    reliability score, a reliability score is standing, and standing is the one
    thing this system exists not to have — see no-gating and no-obligation,
    which forbids the field name outright.

    "You can stop whenever, and nothing is recorded" was a design rule with no
    button for as long as this function did not exist. Now it is operable, and
    the second half of the sentence is true because the row is gone.

    Hours already recorded are untouched. A Contribution points at the posting,
    never at the claim, so work that actually happened survives — that is a
    fact about the world rather than a commitment anybody made.
    """
    claim = Claim.objects.filter(posting=posting, member=member).first()
    if claim is None:
        raise ValueError("You are not on that posting.")

    claim.delete()
    return Claim.objects.filter(posting=posting).count()


def record_contribution(*, member, posting, hours, note="", recorded_at=None):
    """Write down hours that were given, chained to the entry before them.

    `hours` is a duration and never a price. It is not weighted by who gave it,
    and it does not accumulate into anything a member holds — there is no
    balance for it to land in.

    The chain is per organization, so one community's history is verifiable on
    its own and a gap is visible as a missing sequence number.
    """
    if hours <= 0:
        raise ValueError("Hours must be positive.")
    if posting.organization_id != member.organization_id:
        raise ValueError("Posting and member belong to different organizations.")

    recorded_at = recorded_at or datetime.now(timezone.utc)

    # SERIALISED PER ORGANIZATION, because appending to a chain is
    # read-then-write and two people recording hours in the same second both
    # read the same tip. The unique constraint on (organization, sequence)
    # means that can never corrupt the chain — but without a lock the loser
    # gets an IntegrityError, which reaches a member as a 500 with their hours
    # gone. That is the failure on the busiest day, when several people write
    # up a work party at once.
    #
    # The organization row is the lock because the chain is per organization:
    # exactly the granularity that needs ordering, and no more. Organization is
    # not tenant-scoped — it IS the tenant — so this reads without bypass.
    with transaction.atomic():
        Organization.objects.select_for_update().get(pk=member.organization_id)

        previous = (
            Contribution.objects
            .filter(organization_id=member.organization_id)
            .order_by("-sequence")
            .first()
        )
        sequence = (previous.sequence + 1) if previous else 0
        previous_hash = previous.entry_hash if previous else ""

        payload = {
            "member": str(member.id),
            "posting": str(posting.id),
            "hours": _canonical_hours(hours),
            "note": note,
        }
        entry_hash = chain.entry_hash(
            sequence=sequence,
            recorded_at=recorded_at,
            payload=payload,
            previous_hash=previous_hash,
        )

        # Inside the lock: the read of the tip and the write of the next link
        # are one indivisible step, which is the only thing that makes the
        # sequence safe to compute in Python.
        return Contribution.objects.create(
            organization_id=member.organization_id,
            member=member,
            posting=posting,
            hours=hours,
            note=note,
            recorded_at=recorded_at,
            sequence=sequence,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
        )


def verify_contributions(organization):
    """Walk one organization's contribution chain. Returns a ChainReport."""
    entries = [
        {
            "sequence": c.sequence,
            "recorded_at": c.recorded_at,
            "payload": {
                "member": str(c.member_id),
                "posting": str(c.posting_id),
                "hours": _canonical_hours(c.hours),
                "note": c.note,
            },
            "previous_hash": c.previous_hash,
            "entry_hash": c.entry_hash,
        }
        for c in Contribution.objects.filter(organization=organization).order_by("sequence")
    ]
    tip = entries[-1]["entry_hash"] if entries else None
    return chain.verify_chain(entries, expected_tip=tip)
