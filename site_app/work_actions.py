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

from pathlib import Path

from kjerne_platform.work import port

SITE = "dugnadsand"

_WORK_TOML = Path(__file__).resolve().parents[1] / "work.toml"
_BASE = "https://dugnadsand.org"


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


# --------------------------------------------------------------------------
# Asking somebody who has no account
#
# Half the people who could help here will never make a login. The dual path
# sends them two links: one that claims the posting, one that does nothing at
# all. Which is the point — see [settings.tokens] decline in work.toml.
#
# The sender is told nothing. Not whether it arrived, not whether it was
# opened, not which link was pressed. A sender who can see silence will read
# silence as refusal, and being watched for an answer is the obligation this
# site does not have. If the person claims it, it shows up on the board like
# any other claim, which is how anybody else would have found out too.
# --------------------------------------------------------------------------

def invite(*, posting, email, member=None):
    """Send someone without an account a way to take this on. Returns nothing.

    Deliberately returns nothing. A count of who was reached is a delivery
    receipt, and a delivery receipt is the first half of knowing they said no.
    """
    from kjerne_platform import email as mailer
    from kjerne_platform.work import port as work_port
    from kjerne_platform.work import tokens

    p = work_port.open(_WORK_TOML)
    payload = {"item": str(posting.id)}
    if member is not None:
        payload["party"] = str(member.id)

    tenant = posting.organization_id
    yes = tokens.issue(p, verb="claim", payload=payload, tenant=tenant,
                       recipient=email, side=tokens.CONFIRM)
    no = tokens.issue(p, verb="claim", payload=payload, tenant=tenant,
                      recipient=email, side=tokens.DECLINE)

    # Under signal-only the invitation cannot say what the posting is. It does
    # not need to: the question is whether this person wants to look.
    mailer.send(
        to=email,
        subject="Someone nearby could use a hand",
        body=(
            "Somebody on a mutual aid board thought you might be able to help "
            "with something.\n\n"
            f"Yes, I can:  {_BASE}/act/{yes}/\n"
            f"Not this time:  {_BASE}/act/{no}/\n\n"
            "Either link works once. Nobody is told which one you pressed, "
            "and ignoring this mail is a complete answer.\n"
        ),
        site=SITE,
    )


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
