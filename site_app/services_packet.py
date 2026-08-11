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


def add_photo(*, project, member, upload, caption="",
              depicts_people=True):
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
        image=upload, caption=caption.strip()[:300], added_by=member,
        depicts_people=depicts_people)


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
    """Mint the link and put it out, or refuse and say who has not agreed.

    The consent gate is checked HERE rather than in the view, so no caller can
    publish faces by going round the screen — the same reason the unit refusal
    lives in check_unit and not in the form.

    Idempotent: publishing an already-published packet keeps the same token,
    because the link has been sent to people and changing it silently would
    break every copy of it.
    """
    blockers = consent_blockers(packet.project)
    if blockers:
        raise ConsentOutstanding(blockers)

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


# --------------------------------------------------------------------------
# Consent for photographs.
#
# Chained, because consent is the record most worth altering afterwards.
# Somebody who published a picture they should not have has every motive to
# make a consent appear, or a withdrawal vanish. Each entry commits to its
# predecessor, so either shows up as a broken chain and verification says
# where it broke.
#
# It remains evidence of an asking, not proof of an agreement. The chain makes
# it hard to rewrite quietly; it cannot make it true.
# --------------------------------------------------------------------------

class ConsentOutstanding(Exception):
    """Publication refused: somebody in a photograph has not agreed."""

    def __init__(self, blockers):
        self.blockers = blockers
        super().__init__("; ".join(blockers) or "consent outstanding")


def person_digest(name):
    """A KEYED digest of a person's name, for the chain payload.

    Not a plain hash. The name is encrypted at rest, and a bare sha256 in the
    chain would let somebody holding a stolen database confirm a guessed name
    without ever having the encryption key — undoing the encryption through
    the back door of the integrity mechanism. Keyed on SECRET_KEY, which lives
    in the same env file as the encryption key and not in the database.
    """
    import hashlib
    import hmac
    import unicodedata

    from django.conf import settings

    normalized = unicodedata.normalize("NFKC", (name or "").strip()).casefold()
    return hmac.new(settings.SECRET_KEY.encode(), normalized.encode(),
                    hashlib.sha256).hexdigest()


def _consent_payload(*, photo, person, given_on, how, withdrawn_on, note):
    return {
        "photo": str(photo.id),
        "person": person_digest(person),
        "given_on": given_on.isoformat() if given_on else "",
        "how": how,
        "withdrawn_on": withdrawn_on.isoformat() if withdrawn_on else "",
        "note": note,
    }


def _append_consent(*, photo, member, person, given_on=None, how="",
                    withdrawn_on=None, note=""):
    """Append one entry to the organization's consent chain.

    Serialised on the Organization row for the same reason record_contribution
    is: appending is read-then-write, and two people writing up the same work
    party both read the same tip. The unique (organization, sequence)
    constraint means a race can never corrupt the chain, but without the lock
    the loser gets an IntegrityError where a person expected a saved record.
    """
    from django.db import transaction
    from kjerne_platform import chain

    from .models import Organization, PhotoConsent

    recorded_at = _now()

    with transaction.atomic():
        Organization.objects.select_for_update().get(pk=photo.organization_id)

        previous = (PhotoConsent.objects
                    .filter(organization_id=photo.organization_id)
                    .order_by("-sequence").first())
        sequence = (previous.sequence + 1) if previous else 0
        previous_hash = previous.entry_hash if previous else ""

        payload = _consent_payload(
            photo=photo, person=person, given_on=given_on, how=how,
            withdrawn_on=withdrawn_on, note=note)

        return PhotoConsent.objects.create(
            organization_id=photo.organization_id, photo=photo, person=person,
            given_on=given_on, how=how, withdrawn_on=withdrawn_on, note=note,
            recorded_by=member, recorded_at=recorded_at, sequence=sequence,
            previous_hash=previous_hash,
            entry_hash=chain.entry_hash(
                sequence=sequence, recorded_at=recorded_at, payload=payload,
                previous_hash=previous_hash))


def expect_consent(*, photo, member, person, note=""):
    """Say somebody is in the picture, before they have been asked.

    The row exists from that moment, so an unasked person is a visible blocker
    rather than a silence — the same shape as MaterialNeed and Clearance.
    """
    return _append_consent(photo=photo, member=member, person=person, note=note)


def record_consent(*, photo, member, person, given_on, how="", note=""):
    """They agreed. A NEW chain entry, never an edit of the outstanding one.

    Editing in place would leave no trace that the record ever said anything
    else, which is the whole property being bought here.
    """
    return _append_consent(photo=photo, member=member, person=person,
                           given_on=given_on, how=how, note=note)


def withdraw_consent(*, photo, member, person, withdrawn_on, note=""):
    """They changed their mind. Also an append, and it blocks publication."""
    return _append_consent(photo=photo, member=member, person=person,
                           withdrawn_on=withdrawn_on, note=note)


def consent_state(photo):
    """The current position per person: the LAST entry for each one wins.

    Entries are append-only, so a person's standing is whatever their most
    recent row says. Keyed on the digest rather than the name so two spellings
    of one person do not silently become two people — and so this comparison
    never needs the name in the clear.
    """
    latest = {}
    for entry in photo.consents.all().order_by("sequence"):
        latest[person_digest(entry.person)] = entry
    return list(latest.values())


def consent_blockers(project):
    """Why this packet cannot go out yet, named per photograph."""
    reasons = []
    for photo in project.photos.all():
        if not photo.depicts_people:
            continue
        state = consent_state(photo)
        if not state:
            reasons.append(
                f"a photograph shows people and nobody is named on it")
            continue
        for entry in state:
            if entry.withdrawn:
                reasons.append(f"{entry.person} has withdrawn consent")
            elif not entry.given:
                reasons.append(f"{entry.person} has not agreed yet")
    return reasons


def verify_consents(organization_id):
    """Verify the organization's consent chain end to end."""
    from kjerne_platform import chain

    from .models import PhotoConsent

    entries = list(PhotoConsent.objects
                   .filter(organization_id=organization_id)
                   .order_by("sequence"))
    return chain.verify_chain([
        {
            "sequence": e.sequence,
            "recorded_at": e.recorded_at,
            "payload": _consent_payload(
                photo=e.photo, person=e.person, given_on=e.given_on,
                how=e.how, withdrawn_on=e.withdrawn_on, note=e.note),
            "previous_hash": e.previous_hash,
            "entry_hash": e.entry_hash,
        }
        for e in entries
    ])
