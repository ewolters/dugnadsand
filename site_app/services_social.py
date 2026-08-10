"""Saying things, keeping things, and putting facts next to each other.

TWO REFUSALS AND ONE DIVISION OF LABOUR.

**No like.** A like count is a public number attached to a person's
contribution, which is a score wearing a warmer word. Once posts carry visible
counts people write for the counts, and whoever gives quietly ranks below
whoever posts well. There is no like here and there will not be.

**Thanks is not a table.** It is sent and it is gone. That began as a schema
problem — a row with a sender and a recipient has two foreign keys to Member,
which no-exchange flags on sight because a two-party record is how a transfer
looks — and the honest fix turned out to be better than the feature it
replaced. With nothing stored, "never counted, never aggregated, never
displayed" stops being a promise about restraint and becomes a fact about the
schema. Nobody can total what was never written down, including somebody with a
database handle and a grievance.

THE DIVISION OF LABOUR IN PAIRING

The system pairs FACTS. A need with a date approaching and nobody on it. A bill
of materials line and stock recorded in the same unit. Those are coincidences
between two records, and surfacing them is coordination.

People pair PEOPLE. Nothing here ranks a member's suitability, scores them, or
narrows who hears about anything — the moment a pairing consults what somebody
has given it is gating, and the moment it consults tags it has built a catalog.
When a person should be asked, a person asks them: that is point_at(), and
the sender never learns what came of it.
"""

from datetime import date, timedelta
from decimal import Decimal

SITE = "dugnadsand"


# --------------------------------------------------------------------------
# Saying things
# --------------------------------------------------------------------------

def add_comment(*, member, body, posting=None, project=None):
    """Say something about a posting or a project. Exactly one of them."""
    from .models import Comment

    if (posting is None) == (project is None):
        raise ValueError("A comment belongs to exactly one posting or project.")

    body = (body or "").strip()
    if not body:
        raise ValueError("Say something.")

    return Comment.objects.create(
        organization_id=member.organization_id, member=member,
        posting=posting, project=project, body=body)


def say_thanks(*, to_member, from_member):
    """Thank somebody. Sent, and gone.

    Returns nothing. There is no record to return, no id to store and no count
    to increment, which is the point rather than an omission.

    The message names nobody and carries no words of the sender's own, because
    it travels through the shared platform notification table which sits
    outside this site's row-level security. Warmth without content is a real
    constraint and this is the honest version of it: somebody here noticed.
    """
    from kjerne_platform import notify

    user = to_member.user
    if user is None or not user.email:
        return

    if from_member is not None and from_member.id == to_member.id:
        return

    try:
        notify.send(user.email, SITE, "thanks",
                    "Somebody here said thanks.", link="/board/")
    except Exception:  # never fails the page it was sent from
        import logging

        logging.getLogger(__name__).exception("thanks could not be delivered")


def point_at(*, posting, to_member, from_member):
    """Point somebody at a posting. "I thought of you."

    Returns nothing, and that is the design. A count of who was reached is a
    delivery receipt; a delivery receipt is the first half of knowing somebody
    said no; and a sender who can see silence reads silence as refusal. Being
    watched for an answer is the obligation this whole system does not have.
    So the sender learns nothing — not delivery, not opening, not action. If
    the person takes it on, it appears on the board like any other claim, which
    is how anybody else would have found out too.

    A NOTIFICATION, NOT A CAPABILITY, and the difference took a wrong turn to
    find. The first version emailed a stranger two single-use links, one of
    which claimed the posting. It could not work: a claim needs a Member, a
    stranger is not one, and Member carries no email of its own — the address
    lives on the user account a rostered non-user does not have. Redeeming it
    raised TypeError and the page reported "that link is no longer usable",
    which is a dead end wearing a polite sentence.

    The people worth pointing at are members. Members have accounts. That is a
    notice. The token path stays where it genuinely works — receipt
    confirmation, where the recipient is at a loading dock and the address
    comes off the manifest.
    """
    from .notifications import _send

    if to_member.id in (from_member.id, posting.member_id):
        return  # yourself, or the person who wrote it

    user = to_member.user
    email = user.email if user else ""
    if not email:
        return

    # Signal only. Not the posting's words, not who thought of them — the
    # notice travels through the shared platform table, and "somebody thought
    # of you" is enough to make a person look.
    _send(email, "pointed",
          "Somebody thought you might be able to help with something.",
          "/board/")


# --------------------------------------------------------------------------
# Keeping things
# --------------------------------------------------------------------------

def toggle_pin(*, member, posting=None, project=None):
    """Bookmark, or un-bookmark. Private to its owner.

    A public pin would be editorial ranking — the like problem with an editor,
    where what gets attention is decided by whoever pins rather than whoever
    needs. Nothing counts these and nothing displays them to anybody else.
    """
    from .models import Pin

    if (posting is None) == (project is None):
        raise ValueError("Pin exactly one posting or project.")

    existing = Pin.objects.filter(
        member=member, posting=posting, project=project).first()
    if existing is not None:
        existing.delete()
        return False

    Pin.objects.create(
        organization_id=member.organization_id, member=member,
        posting=posting, project=project)
    return True


def pinned_for(member):
    """This member's own bookmarks. Never anybody else's."""
    from .models import Pin

    return (Pin.objects.filter(member=member)
            .select_related("posting", "project", "posting__member"))


# --------------------------------------------------------------------------
# Pairing facts
#
# Everything below joins two RECORDS. None of it reads a person, so none of it
# can rank one. If a function here ever needs to know who somebody is in order
# to decide what to surface, it has stopped being coordination.
# --------------------------------------------------------------------------

def running_out(*, within_days=3):
    """Open needs whose date is close, that nobody has taken up.

    The pairing of a need with TIME. Both halves matter: a need with a date
    approaching is urgent, and a need with somebody already on it is handled.
    Only the intersection is worth anybody's attention.

    Ordered by date. Never by who asked — a queue sorted by its askers'
    standing is gating with a scheduler attached.
    """
    from .models import Posting

    horizon = date.today() + timedelta(days=within_days)
    postings = (Posting.objects.filter(kind=Posting.NEED, open=True,
                                       needed_by__isnull=False,
                                       needed_by__lte=horizon)
                .select_related("member").prefetch_related("claims"))
    return sorted((p for p in postings if not p.claims.all()),
                  key=lambda p: p.needed_by)


def fillable_needs():
    """Bills of material that stock on hand could satisfy, in whole or part.

    The pairing of a need with RESOURCES, and it matches on UNIT rather than on
    description. That is deliberate and it is the safe half of the idea: a unit
    is a word a member typed — board-feet, pallets, cases — so matching equal
    units is matching two facts, not classifying either.

    Matching descriptions would need a vocabulary of materials to compare
    against, and a vocabulary makes two donations comparable, and comparables
    have a price. See no-catalog. If this ever needs to be cleverer, the answer
    is a better search box for a person, not a better classifier for a machine.

    Returns (need, [lines]) for needs with something outstanding.
    """
    from .models import MaterialNeed, StockLine

    stock = list(StockLine.objects.filter(available=True)
                 .select_related("warehouse", "warehouse__holder"))
    by_unit = {}
    for line in stock:
        by_unit.setdefault(line.unit.strip().lower(), []).append(line)

    pairs = []
    for need in (MaterialNeed.objects.filter(project__open=True)
                 .select_related("project").prefetch_related("given")):
        if need.remaining <= Decimal("0.00"):
            continue
        lines = by_unit.get(need.unit.strip().lower())
        if lines:
            pairs.append((need, lines))
    return pairs


def going_quiet(*, days=21):
    """Stock nobody has confirmed in a while.

    Not a pairing but the same family: a fact about a record, surfaced so a
    person can act on it. Somebody has to be asked whether the pallet is still
    there, and the only person who can answer is its holder.
    """
    from .models import StockLine

    lines = (StockLine.objects.filter(available=True)
             .select_related("warehouse", "warehouse__holder"))
    return sorted((line for line in lines if line.confirmed_days_ago >= days),
                  key=lambda line: line.confirmed_at)
