"""Work days, and the permission to hold one.

A work day is announced to people who will then arrange their Sunday around
it. Announcing one the organization has no right to hold is how a community
ends up standing at a locked gate, or in a river it was not cleared to be in,
without the insurance anybody assumed was in place.

So publication is the one operation here that can be refused, and it is
refused for exactly one reason: an outstanding or lapsed clearance. The gate
reads the clearance table and nothing else. It cannot read a member, a
contribution or a claim, and test_events.py holds that by watching the SQL --
because a gate that grew a second input would be a different thing wearing
this one's name.

The refusal this module makes: recording a clearance does not create one. What
is stored is that somebody says permission was given, plus a reference so the
claim can be checked by a person who was not on the call. Nothing here
verifies anything with a county.
"""

from datetime import datetime, timezone

from .models import Clearance, WorkDay


class NotCleared(Exception):
    """Publication refused: something outside has not said yes yet."""

    def __init__(self, blockers):
        self.blockers = blockers
        super().__init__(
            "; ".join(f"{c.kind} from {c.authority}" for c in blockers)
            or "not cleared")


def _now():
    return datetime.now(timezone.utc)


def call_work_day(*, organization, member, name, description, starts_at,
                  place, ends_at=None, muster="", project=None):
    """Put a day in the calendar. Unpublished: nobody is told yet."""
    return WorkDay.objects.create(
        organization=organization, project=project, name=name,
        description=description, starts_at=starts_at, ends_at=ends_at,
        place=place, muster=muster, called_by=member)


def require_clearance(*, work_day, member, kind, authority, note=""):
    """Raise a requirement before anybody has asked for it.

    The row exists from the moment somebody realises it is needed, which is
    the point: an unasked question is visible as a blocker rather than as
    nothing at all.
    """
    return Clearance.objects.create(
        organization=work_day.organization, work_day=work_day, kind=kind,
        authority=authority, note=note, raised_by=member)


def record_clearance(*, clearance, obtained_on, reference="",
                     expires_on=None, note=None):
    """Somebody said yes. Record when, and how the claim can be checked.

    Takes no member. An earlier signature recorded who obtained it, which put
    a second Member FK on the row, and no-exchange refused that outright --
    two member links is the shape of a transfer. Who spoke to the authority
    belongs in note, where it is a sentence rather than a relation.
    """
    clearance.obtained_on = obtained_on
    clearance.reference = reference
    clearance.expires_on = expires_on
    if note is not None:
        clearance.note = note
    clearance.save(update_fields=["obtained_on", "reference",
                                  "expires_on", "note"])
    return clearance


def publish(work_day):
    """Announce it, or refuse and say what is missing.

    Idempotent: publishing an already-published day does not move the
    timestamp, so a double submit cannot make a day look newly announced.
    """
    blockers = work_day.blockers
    if blockers:
        raise NotCleared(blockers)
    if work_day.published_at is None:
        work_day.published_at = _now()
        work_day.save(update_fields=["published_at"])
    return work_day


def cancel(work_day, *, because=""):
    """Off. A timestamp and a reason, not a status with a workflow."""
    work_day.cancelled_at = _now()
    work_day.cancelled_because = because
    work_day.save(update_fields=["cancelled_at", "cancelled_because"])
    return work_day


# --------------------------------------------------------------------------
# Turning up. The social half of a work day, and the one it never had.
# --------------------------------------------------------------------------

class DayCalledOff(Exception):
    """Nobody comes to a day that was called off."""


def coming(*, day, member, bringing=""):
    """Say you will be there, and optionally what you are bringing.

    Saying it again updates what you are bringing rather than adding a second
    row, so somebody can change their mind about the trailer without it
    reading as two people.

    A CANCELLED DAY REFUSES. Somebody arriving at a called-off day because
    the button still worked is the failure this exists to prevent, and it is
    the only refusal here -- there is no ceiling on how many can come, no
    deadline after which it closes, and no permission needed from whoever
    called it.
    """
    from .models import Attending

    if day.cancelled_at is not None:
        raise DayCalledOff("That day was called off.")

    attending, created = Attending.objects.get_or_create(
        day=day, member=member,
        defaults={"organization_id": member.organization_id,
                  "bringing": bringing.strip()[:200]})
    if not created and attending.bringing != bringing.strip()[:200]:
        attending.bringing = bringing.strip()[:200]
        attending.save(update_fields=["bringing"])
    return attending


def not_coming(*, day, member):
    """A HARD DELETE, like stepping off a claim.

    No cancelled flag, no attended flag, nothing recording that somebody said
    they would come and then did not. That record is a reliability score with
    a friendlier name, and a day where changing your mind costs something is
    a day people stop answering honestly.
    """
    from .models import Attending

    Attending.objects.filter(day=day, member=member).delete()
