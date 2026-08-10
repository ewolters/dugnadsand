"""What this site lets the shared port do on its behalf.

Every verb here is a thin translation from contract vocabulary into this site's
own service layer, and that is the entire point. The port deliberately cannot
write — see kjerne_platform/work/port.py — because a generic writer would
insert Claim rows without going through claim_posting, and claim_posting being
four lines that never import Contribution is the thing the policy manifest
proves. A shortcut past the service layer is a shortcut past no-gating.

Notice which verbs are absent. There is no `assign`, because nobody may be put
on something by anybody else. There is no `complete`, because a recorded
completion is a recorded duty that was owed. An adapter asking for either gets
VerbNotBound naming what IS available, rather than a silent generic write — a
refusal is a better answer than an accommodation here.
"""

from kjerne_platform.work import port

SITE = "dugnadsand"


@port.tenant_scope(SITE)
def _scope(tenant):
    """How this site enters the tenant a token carries.

    The only privileged step in the whole dual path, and it is narrow on
    purpose: one lookup of one organization by the id the token was issued
    with. Everything the verb then does runs inside normal row-level security,
    exactly as it would for a signed-in member.
    """
    from .models import Organization
    from .tenancy import bypass_rls, tenant_context

    with bypass_rls():
        org = Organization.objects.get(pk=tenant)
    return tenant_context(org)


def _resolve(model, value):
    """Accept either a row or its id, so an adapter need not hold Django objects."""
    return value if isinstance(value, model) else model.objects.get(pk=value)


@port.action(SITE, "claim")
def claim(*, item, party):
    """Be the one on this. Never consults what the party has given."""
    from .models import Member, Posting
    from .notifications import announce_claim
    from .services import claim_posting

    posting = _resolve(Posting, item)
    member = _resolve(Member, party)
    result = claim_posting(posting=posting, member=member)
    announce_claim(result)
    return result


@port.action(SITE, "step-off")
def step_off(*, item, party):
    """Stop being the one on this. Deletes the row; nothing is recorded."""
    from .models import Member, Posting
    from .notifications import announce_uncovered
    from .services import step_off as do_step_off

    posting = _resolve(Posting, item)
    member = _resolve(Member, party)
    remaining = do_step_off(posting=posting, member=member)
    if remaining == 0:
        announce_uncovered(posting)
    return remaining


@port.action(SITE, "record-entry")
def record_entry(*, item, party, hours, note=""):
    """Hours that were actually given. Flat, unweighted, undenominated."""
    from decimal import Decimal

    from .models import Member, Posting
    from .services import record_contribution

    return record_contribution(
        posting=_resolve(Posting, item), member=_resolve(Member, party),
        hours=Decimal(str(hours)), note=note)


@port.action(SITE, "confirm-receipt")
def confirm_receipt(*, manifest, note=""):
    """Somebody at the far end signed for it.

    The one place a capability genuinely belongs. Whoever takes delivery is
    standing in a yard with a phone and very often has no account here;
    requiring one means the receipt never gets recorded, and an unrecorded
    receipt is the thing a donating business needed this for.

    Unlike claiming, this needs no Member — which is exactly why the token path
    works here and could not work for an invitation.
    """
    from .models import Manifest
    from .services_warehouse import receive_material

    return receive_material(manifest=_resolve(Manifest, manifest), note=note)


@port.action(SITE, "close-item")
def close_item(*, item, party):
    """Take it off the board. Only the person who posted it, and it records
    no outcome — closed means off the board, never fulfilled."""
    from .models import Member, Posting

    posting = _resolve(Posting, item)
    member = _resolve(Member, party)
    if posting.member_id != member.id:
        raise PermissionError("Only the person who posted it can take it down.")
    posting.open = False
    posting.save(update_fields=["open"])
    return posting
