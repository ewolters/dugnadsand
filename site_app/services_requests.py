"""Requests for help, and who is allowed to answer one.

Somebody who needs help does not join anything. They write what they need and
how to reach them, and that is the last this system asks of them.

Two rules hold everything else up:

  A request is BLIND. The need and a coarse area are shown. The name and the
  way to reach them are withheld from everybody until one group takes it up,
  and then shown to that group alone.

  Only a VETTED MUTUAL AID GROUP may take one. Not a business, not a
  household, not a chapter officer by virtue of the role. The vetting is done
  by a person and recorded on the organization, and this module refuses on
  the stored fact rather than on anybody's good intentions.
"""

from datetime import datetime, timezone


class NotAnAidGroup(Exception):
    """Only a vetted mutual aid group may take up a request."""


class AlreadyTaken(Exception):
    """Another group reached it first."""


def _now():
    return datetime.now(timezone.utc)


def submit_request(*, need, reach_them, asked_by="", area="", region=None):
    """Record a request. No account, no membership, no tenant.

    Everything identifying is encrypted at rest and stays withheld until a
    group takes it up.
    """
    from .models import Request

    need = (need or "").strip()
    reach_them = (reach_them or "").strip()
    if not need:
        raise ValueError("Say what is needed.")
    if not reach_them:
        raise ValueError("Say how somebody can get back to you.")

    return Request.objects.create(
        need=need, reach_them=reach_them, asked_by=asked_by.strip()[:200],
        area=area.strip()[:120], region=region)


def visible_to(member):
    """The requests this member's organization may see.

    A request is only ever visible to aid groups in its own chapter. Everybody
    else — businesses, households, and anybody with no chapter — gets nothing,
    which is the safe direction: a feed that leaks who is struggling on which
    street is worse than a feed that shows too little.
    """
    from .models import Request

    organization = member.organization
    if not organization.is_aid_group or organization.region_id is None:
        return Request.objects.none()

    return (Request.objects
            .filter(region_id=organization.region_id, closed_at__isnull=True)
            .select_related("taken_by"))


def take_request(*, request, member):
    """A group takes it up, and only then sees how to reach the person.

    Refused for anybody who is not a vetted aid group, and refused if another
    group reached it first — the second refusal is not politeness, it stops
    two groups turning up at one door.
    """
    from django.db import transaction

    from .models import Request

    organization = member.organization
    if not organization.is_aid_group:
        raise NotAnAidGroup(
            "Only a vetted mutual aid group can take up a request.")
    if organization.region_id != request.region_id:
        raise NotAnAidGroup("That request is not in this chapter.")

    with transaction.atomic():
        # Locked and re-read: two groups pressing at once must not both win.
        fresh = Request.objects.select_for_update().get(pk=request.pk)
        if fresh.taken_by_id is not None:
            raise AlreadyTaken(
                "Another group has already taken this one up.")
        fresh.taken_by = organization
        fresh.taken_at = _now()
        fresh.save(update_fields=["taken_by", "taken_at"])

    # The caller is usually still holding the instance it passed in. Leaving
    # it stale is how the release check above got written wrong the first time.
    request.taken_by = organization
    request.taken_at = fresh.taken_at
    return fresh


def release_request(*, request, member):
    """Put it back. Nothing records that it was ever held.

    A group that finds it cannot help must be able to say so without that
    becoming a mark against them or against the person who asked.
    """
    from .models import Request

    # Conditioned on the stored holder rather than on the instance handed in.
    # An instance can be stale -- take_request writes a re-read row, so a
    # caller still holding the object it passed sees taken_by as None -- and
    # a permission check that reads a stale copy is a permission check that
    # can be wrong in both directions.
    changed = (Request.objects
               .filter(pk=request.pk, taken_by=member.organization_id)
               .update(taken_by=None, taken_at=None))
    if not changed:
        raise NotAnAidGroup("Only the group holding it can put it back.")


def close_request(*, request, member):
    """Off the list. NO OUTCOME IS RECORDED.

    What happened between a group and a person is theirs. A field for it would
    be this system reaching into the last mile, which is the one thing the
    policy says it does not do.
    """
    from .models import Request

    changed = (Request.objects
               .filter(pk=request.pk, taken_by=member.organization_id)
               .update(closed_at=_now()))
    if not changed:
        raise NotAnAidGroup("Only the group holding it can close it.")
