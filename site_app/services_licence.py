"""Offering skilled work, under the licence you hold to do it.

An electrician offering an evening on this board is offering it as an
electrician. The offer is free; the licence is not suspended because the work
is unpaid, and nobody's homeowner's insurance cares that the panel was rewired
as a favour.

So: an organization admitted with a verified licence cannot post an offer or
put its name to one without saying, in that moment, that the offer stands
under that licence. The words are shown, the tick is required, and what was
ticked is snapshotted onto the record as text.

WHAT THIS IS NOT. It is not a check that the work is within scope, not a
warranty, and not a claim that anybody verified today what an officer verified
in March. It records an attestation by the person offering, which is the only
thing a system on this side of the wire can honestly hold.

Most people hold no licence, and for them none of this appears. It is not a
rank: nothing sorts by it, nothing filters by it, and an offer of an evening's
wiring sits in the same feed in the same order as an offer of a lift.
"""


class LicenceNotAffirmed(Exception):
    """A licence is held and the offer did not stand under it."""


def label(credential):
    """How one licence is named, on screen and in the snapshot.

    kind and authority only. reference holds the number on the document, and
    for some organizations that number is a tax identification number -- the
    single most sensitive value stored here. It has no business being on a
    posting that a whole chapter reads.
    """
    kind = (credential.kind or "").strip()
    authority = (credential.authority or "").strip()
    return f"{kind} ({authority})" if authority else kind


def held_by(organization):
    """The licence labels this organization currently holds, or []."""
    return [label(c) for c in organization.licences()]


def sentence(organization):
    """The words somebody is agreeing to, or None if none are needed."""
    labels = held_by(organization)
    if not labels:
        return None
    return (f"This is offered under {organization.name}'s "
            f"{', and '.join(labels)}, and within what that licence covers.")


def snapshot(organization, affirmed):
    """What to store on the record, given what was ticked.

    Returns "" for an organization holding no licence, which is most of them.
    Raises when a licence is held and the tick is absent, rather than storing
    a blank and letting the offer stand: the blank would be indistinguishable
    afterwards from an offer by somebody who holds nothing.
    """
    labels = held_by(organization)
    if not labels:
        return ""
    if not affirmed:
        raise LicenceNotAffirmed(
            "An offer from a licensed organization stands under that licence.")
    return ", and ".join(labels)[:200]
