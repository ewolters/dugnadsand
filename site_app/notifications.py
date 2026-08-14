"""Telling people something is here.

A board nobody is told about is a noticeboard in an empty hallway. Everything
else in this app was built before this module existed, which meant a need could
sit open for a week because the two people who could have met it did not happen
to log in. That is the failure this closes.

Three rules govern what goes out, and all three are load-bearing.

**Recipients are never chosen by what someone has given.**
The tempting feature is to route a need to whoever gives most, or to whoever
has "capacity". Both make the ledger into standing, which is the single thing
this system exists not to do — see policy/manifest.toml, no-gating. Everyone in
the organization hears; who responds is theirs to decide. If you are here to
add relevance ranking, read the manifest first.

**Nothing tenant-scoped goes into the message body.**
kjerne_platform.notify writes to the shared platform database, keyed by email,
alongside every other federation site's notices. Postgres RLS does not reach
there. So a notice carries the SIGNAL — a need appeared, it is wanted soon —
and never the free text or the member's name. Those stay behind RLS, and the
link fetches them under the reader's own session. A notice is a knock on the
door, not the letter.

**A failed notice never fails the thing it was about.**
Posting help is the point; being told is the service. If the platform database
is unreachable, the posting still stands and the error goes to the log.
"""

import logging

logger = logging.getLogger(__name__)

SITE = "dugnadsand"


def _audience(organization_id, exclude_member_id=None):
    """Everyone in the organization with an email, except one person.

    Deliberately a flat select. There is no ordering, no scoring and no filter
    beyond "is a member here and can be reached" — see the module docstring.
    RLS scopes this to the caller's organization already; organization_id is
    passed explicitly so the query is correct even outside a request.
    """
    from .models import Member

    # user__isnull=False is not redundant with the exclude below it. A Member
    # can exist with no user — someone on the roster who has never signed in —
    # and across a nullable FK Django renders exclude() as a LEFT JOIN where
    # NULL = '' is NULL, so NOT(NULL) is NULL and the row survives the filter.
    # It reads like it covers the case. It does not.
    members = (
        Member.objects.filter(organization_id=organization_id, user__isnull=False)
        .exclude(user__email="")
        .select_related("user")
    )
    if exclude_member_id is not None:
        members = members.exclude(pk=exclude_member_id)
    return members


def _send(email, kind, message, link):
    """One notice, fail-open. Returns True if it went out."""
    from kjerne_platform import notify

    try:
        notify.send(email, SITE, kind, message, link=link)
        return True
    except Exception:
        logger.exception("notify failed for %s (%s)", email, kind)
        return False


# --------------------------------------------------------------------------
# Reading notices back — scoped to this site
#
# kjerne_platform.notify keys everything on email ALONE. recent(),
# unread_count() and mark_read() deliberately span the whole federation, so
# that a notice raised on one site surfaces wherever you sign in. That is the
# right default for the federation and the wrong one here.
#
# A dugnadsand member is very often also a svend or kjerne-services user under
# the same address. Unscoped, this app's notice page would show them another
# product's notices, its badge would count them, and opening it would mark them
# read — clearing an alert they had never seen, from a site with no business
# touching it.
#
# So reads are filtered to SITE. The library is left alone; this is a property
# of what dugnadsand is, not a defect in the shared code.
# --------------------------------------------------------------------------

def _platform_cursor():
    from kjerne_platform.db import get_conn
    return get_conn()


def unread_here(email):
    """Unread notices raised BY THIS SITE. Fails open at zero."""
    if not email:
        return 0
    try:
        with _platform_cursor() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM notification "
                "WHERE recipient_email = %s AND site = %s AND read_at IS NULL",
                (email, SITE))
            return cur.fetchone()[0]
    except Exception:
        logger.warning("unread count unavailable", exc_info=True)
        return 0


def recent_here(email, limit=50):
    """Newest-first notices from this site. Raises — the view decides."""
    with _platform_cursor() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, kind, message, link, read_at, created_at FROM notification "
            "WHERE recipient_email = %s AND site = %s "
            "ORDER BY created_at DESC, id DESC LIMIT %s",
            (email, SITE, limit))
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def already_pending(email, kind):
    """Is there an unread notice of exactly this kind waiting already?

    THE NUDGE THAT REPEATS. The warehouse sweep runs nightly and asked every
    holder about every quiet stock line, every night, with an identical
    sentence -- so a member with two quiet pallets opened the page to four
    copies of "Something you are holding has not been confirmed in a while",
    then eight, then twelve. A notice feed that repeats itself is unread
    within a week, and then the one notice that mattered is unread too.

    Fails open at False: a platform outage should let a nudge through twice,
    never swallow it. The wrong direction here is silence.
    """
    if not email:
        return False
    try:
        with _platform_cursor() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM notification "
                "WHERE recipient_email = %s AND site = %s AND kind = %s "
                "AND read_at IS NULL LIMIT 1",
                (email, SITE, kind))
            return cur.fetchone() is not None
    except Exception:
        logger.warning("pending check unavailable", exc_info=True)
        return False


def mark_read_here(email, ids):
    """Mark specific notices read.

    ids is required and never defaulted. notify.mark_read(email) with no ids
    clears every site's notices for that address, which from here would be
    reaching into another product to dismiss an alert nobody here has seen.
    """
    from kjerne_platform import notify

    if not ids:
        return
    notify.mark_read(email, ids=ids)


def badge(request):
    """Context processor: unread count for this site on every render.

    Replaces kjerne_platform.notify.notifications, which counts federation
    wide. Fails open — a platform outage must not take rendering down.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"notifications_unread": 0}
    return {"notifications_unread": unread_here(user.email)}


def _when(posting):
    """The urgency suffix, or nothing. Never the description."""
    word = posting.urgency
    if word == "whenever":
        return ""
    if word == "overdue":
        return " — the date on it has passed"
    if word == "later":
        return ""
    return f" — wanted {word}"


def announce_posting(posting):
    """Tell the rest of the organization that something appeared.

    Sent to everyone but the poster. Returns the number of notices delivered,
    which is for tests and logs — no caller shows it to a member, because a
    sender who can see reach can infer silence, and silence would start to look
    like refusal. See the poke design note in docs/design-rules.md.
    """
    from .models import Posting

    if posting.kind == Posting.NEED:
        message = f"Someone here needs a hand{_when(posting)}."
    else:
        message = f"Someone here is offering something{_when(posting)}."

    sent = 0
    for member in _audience(posting.organization_id, posting.member_id):
        if _send(member.user.email, "posting", message, "/board/"):
            sent += 1
    return sent


def announce_uncovered(posting):
    """Tell the poster nobody is on their posting any more.

    Sent only when the last person steps off, and phrased as a STATE rather
    than an event: "nobody is on this at the moment", never "somebody stepped
    off". The difference is not politeness. An event has a subject, and a
    notice whose subject is a person who stopped is a notice that somebody let
    you down — which puts the obligation back that step_off() exists to remove.

    Silence would be worse than either. If you asked for a ride on Thursday and
    your driver quietly stepped off, not being told is a real harm, and it is
    the poster's own posting rather than anyone else's business.

    Only fires at zero. Two people on a need, one steps off, it is still
    covered and there is nothing to say.
    """
    poster = posting.member.user
    email = poster.email if poster else ""
    if not email:
        return 0

    if posting.kind == posting.NEED:
        message = "Nobody is on what you asked for at the moment."
    else:
        message = "Nobody is on what you offered at the moment."

    return 1 if _send(email, "uncovered", message, "/board/") else 0


def announce_booked_out(manifest):
    """Tell whoever holds a place that material has been booked out of it.

    NOT an approval step. Anyone here may send material from anyone's
    warehouse, and that is right — it is on offer, and making a holder approve
    each release would put a gate in front of a gift. But the goods are in
    their barn, somebody is going to turn up for them, and finding that out
    when a van arrives is not a system anybody would trust twice.

    So: told, never asked. The same shape as everything else here — the board
    does not request permission either, it says what happened.

    Nothing is sent when the holder is the one who sent it.
    """
    warehouse = manifest.stock_line.warehouse
    if warehouse.holder_id == manifest.sent_by_id:
        return 0

    holder = warehouse.holder.user
    email = holder.email if holder else ""
    if not email:
        return 0

    # Signal only. Not what was taken, not who took it, not where it went —
    # all three are tenant text, and the link resolves them under the reader's
    # own session. "Something left your place" is enough to make somebody look.
    return 1 if _send(email, "booked-out",
                      "Material has been booked out of a place you hold.",
                      "/warehouse/") else 0


def announce_project(project):
    """Tell the organization something ongoing has started.

    The name is NOT carried, and the argument for carrying it is worth writing
    down because it is a good one and it is wrong. A project name is the handle
    people use to talk about the work out loud, so a notice without it is
    thinner than it could be. But "Rebuilding the Hendersons' roof after the
    fire" is a project name, and it is exactly as much somebody's circumstances
    as any posting description. There is no test that can tell the two apart,
    which means the exception could not be enforced even if it were right.

    A rule with no exceptions is a rule nobody has to argue about at review
    time. The link resolves the name under the reader's own session.
    """
    message = "Something ongoing started here."
    sent = 0
    for member in _audience(project.organization_id, project.started_by_id):
        if _send(member.user.email, "project", message, f"/projects/{project.id}/"):
            sent += 1
    return sent


def announce_claim(claim):
    """Tell the poster that somebody is on it.

    The claimer's name is not in the message — see the module docstring. The
    poster follows the link and reads it under their own session, inside their
    own tenant, which is where that fact belongs.
    """
    from .models import Posting

    posting = claim.posting
    # Same nullable-user case as _audience: a posting can be made on behalf of
    # someone on the roster who has never signed in, and there is nowhere to
    # send their notice.
    poster = posting.member.user
    email = poster.email if poster else ""
    if not email:
        return 0

    if posting.kind == Posting.NEED:
        message = "Someone is helping with what you asked for."
    else:
        message = "Someone would like what you offered."

    return 1 if _send(email, "claim", message, "/board/") else 0
