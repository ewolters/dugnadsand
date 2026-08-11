"""The impact packet: what a project sends back to everybody who helped.

The consideration in this system is a documented outcome, never a receipt.
Somebody who gives a pallet of shingles gets evidence of what the work
achieved, with photographs, and never a figure they could put on a tax
return -- this system does not know what anything was worth and is built so
it cannot learn.

Two refusals live here, and they are the reason a packet is admissible at all:

  A measure may not be denominated in MONEY. A figure in dollars against
  donated material is an appraisal of donated property produced by a platform
  concerning a donor, which is the one document this system must never make.

  A measure may not be denominated in HOURS. A per-project labour total looks
  safe because it describes work rather than a person -- but a project with
  one contributor IS that contributor's total, and no-aggregate-display exists
  to stop precisely that number existing. Measures describe the outcome, so
  they stay facts about a river rather than about anybody who stood in it.
"""

import re
import secrets
from datetime import datetime, timezone

from .models import Measure, Packet, Photo


class UnitRefused(ValueError):
    """A measure was denominated in something this system does not count in."""


# Deliberately broad, and matched on the whole unit rather than a substring
# boundary in places where a false positive is the safe direction. Somebody
# who genuinely means "labour-days" can say "days".
_MONEY = re.compile(
    r"\b(dollars?|usd|cad|eur|gbp|pounds?|euros?|cents?|money|cash|"
    r"price[ds]?|cost|costs|value|valued|worth|"
    r"retail|msrp|fmv|market)\b|[$€£¥]", re.I)

_HOURS = re.compile(
    r"\b(hours?|hrs?|man[- ]?hours?|person[- ]?hours?|volunteer[- ]?hours?|"
    r"labou?r[- ]?hours?|shifts?|workdays?|man[- ]?days?)\b", re.I)


def check_unit(unit):
    """Refuse a unit that turns a measure into a price or a labour total."""
    unit = (unit or "").strip()
    if not unit:
        raise UnitRefused("Say what it is counted in.")
    if _MONEY.search(unit):
        raise UnitRefused(
            "Measures are not counted in money. A figure in currency against "
            "donated work or material would be an appraisal, which this "
            "system does not produce — see no-material-valuation.")
    if _HOURS.search(unit):
        raise UnitRefused(
            "Measures are not counted in hours. A project total of hours is "
            "one contributor's total whenever there is one contributor — see "
            "no-aggregate-display. Record what the work achieved instead.")
    return unit


def _now():
    return datetime.now(timezone.utc)


def record_measure(*, project, member, label, quantity, unit, note=""):
    """Something true about the world after the work.

    Typed by a person. Nothing here reads the ledger, and nothing computes a
    measure from what anybody gave.
    """
    return Measure.objects.create(
        organization_id=project.organization_id, project=project,
        label=label.strip(), quantity=quantity, unit=check_unit(unit),
        note=note, recorded_by=member)


def add_photo(*, project, member, upload, caption=""):
    """A picture of the work, validated before it is written anywhere.

    Uses the federation's shared upload validation rather than trusting the
    declared type: the content is re-decoded, so a .jpg that is not an image
    is refused here instead of at whatever reads it next.
    """
    from kjerne_platform import uploads

    uploads.validate(
        filename=getattr(upload, "name", ""), size=getattr(upload, "size", None),
        content_type=getattr(upload, "content_type", ""), kind="image",
        fileobj=upload.file if hasattr(upload, "file") else None)

    return Photo.objects.create(
        organization_id=project.organization_id, project=project,
        image=upload, caption=caption.strip()[:300], added_by=member)


def build_packet(*, project, member, title, summary, acknowledgements=""):
    """Write or rewrite the packet for a project. Publication is separate."""
    packet, _created = Packet.objects.get_or_create(
        project=project,
        defaults={"organization_id": project.organization_id,
                  "title": title.strip(), "summary": summary})
    packet.title = title.strip()
    packet.summary = summary
    packet.acknowledgements = acknowledgements
    packet.save(update_fields=["title", "summary", "acknowledgements"])
    return packet


def publish_packet(*, packet, member):
    """Mint the link and put it out.

    Idempotent: publishing an already-published packet keeps the same token,
    because the link has been sent to people and changing it silently would
    break every copy of it.
    """
    if not packet.published:
        packet.token = secrets.token_urlsafe(32)
        packet.published_at = _now()
        packet.published_by = member
        packet.save(update_fields=["token", "published_at", "published_by"])
    return packet


def withdraw_packet(packet):
    """Take it down, and kill the link rather than leaving it working.

    The token is cleared, not kept. Re-publishing mints a new one, so a link
    somebody was given before a withdrawal never starts working again.
    """
    packet.token = ""
    packet.published_at = None
    packet.save(update_fields=["token", "published_at"])
    return packet


def material_for(project):
    """What arrived, described and counted. Never valued, never summed.

    Returns the individual arrivals rather than a total per line: a total
    would be a figure about the requirement, which is fine, but the packet
    reads better as a record of things that turned up and the distinction is
    not worth a second aggregate to defend.
    """
    from .models import MaterialGiven

    return (MaterialGiven.objects
            .filter(need__project=project)
            .select_related("need")
            .order_by("recorded_at"))
