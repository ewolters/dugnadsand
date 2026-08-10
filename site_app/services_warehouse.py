"""The virtual warehouse: what happens to material, and what never does.

Three operations and one refusal.

We never take custody. Goods stay where their holder keeps them; this records a
location, a description and a count. That is the whole legal shape — no custody
means no title, and no title means no storage liability, no insurance
obligation and no unrelated-business exposure. The platform stays a directory,
which is the same posture that keeps hours a record rather than a currency.

The refusal: nothing here prices anything, and nothing converts material into
hours. A manifest proves goods MOVED. What they were worth is between the
donor, their advisor and the IRS — see no-material-valuation.
"""

from datetime import datetime, timezone
from decimal import Decimal

from .models import Manifest, StockLine


def _now():
    return datetime.now(timezone.utc)


def confirm_line(*, line, member, quantity=None):
    """The holder saying "this is still true, and here is what is left".

    Re-confirming is the only thing that moves the freshness clock. Everything
    a page shows about a quantity is really a claim about when a person last
    looked at it, so the person has to be the one who moves it.
    """
    if quantity is not None:
        line.quantity = Decimal(str(quantity))
    line.confirmed_at = _now()
    line.confirmed_by = member
    line.available = line.quantity > 0
    line.save(update_fields=["quantity", "confirmed_at", "confirmed_by", "available"])
    return line


def send_material(*, line, quantity, destination, member):
    """Book material out of a warehouse toward somebody who needs it.

    Reduces the recorded quantity and DELIBERATELY DOES NOT touch confirmed_at.
    The sender knows what they sent; they have not re-counted what is left, and
    letting a shipment refresh the clock would make the shelf look freshly
    checked because something left it. Only a holder looking at the shelf
    resets that.
    """
    quantity = Decimal(str(quantity))
    if quantity <= 0:
        raise ValueError("Send an amount greater than zero.")
    if quantity > line.quantity:
        raise ValueError(
            f"There are only {line.quantity} {line.unit} recorded on that line.")

    manifest = Manifest.objects.create(
        organization_id=line.organization_id,
        stock_line=line, quantity=quantity,
        destination=destination, sent_by=member)

    # Somebody is going to turn up at their barn for this. Told, never asked —
    # see notifications.announce_booked_out.
    from .notifications import announce_booked_out

    announce_booked_out(manifest)

    line.quantity = line.quantity - quantity
    line.available = line.quantity > 0
    line.save(update_fields=["quantity", "available"])
    return manifest


def receive_material(*, manifest, note=""):
    """Signed for at the other end.

    Idempotent on purpose: a QR gets scanned twice, by two people, on a loading
    dock. The first scan is the receipt and the second is a no-op rather than
    an error, because an error message on a phone in a yard helps nobody.
    """
    if manifest.received_at is not None:
        return manifest

    manifest.received_at = _now()
    manifest.received_note = note or ""
    manifest.save(update_fields=["received_at", "received_note"])
    return manifest


def available_lines(organization_id=None):
    """Everything on offer, freshest confirmation first.

    Ordered by confirmation rather than quantity or recency, because the
    question a reader actually has is "can I rely on this", and the answer to
    that is how recently somebody looked.
    """
    lines = StockLine.objects.filter(available=True).select_related(
        "warehouse", "warehouse__holder", "confirmed_by")
    if organization_id is not None:
        lines = lines.filter(organization_id=organization_id)
    return lines.order_by("-confirmed_at")


# --------------------------------------------------------------------------
# Bills of material
#
# Two logs on a project — hours and material — adjacent and never summed. The
# conversion between them is what would turn both into a price, so there is no
# function here that takes one and returns the other, and there never may be.
# --------------------------------------------------------------------------


def record_material(*, need, member, quantity, note="", manifest=None):
    """Material that actually arrived against a line on a bill of materials.

    No valuation, no hour equivalence, and no arithmetic against the hours
    ledger — see no-material-valuation, which fails on a relation to
    Contribution as readily as on a field called `value`.

    Over-delivery is allowed. Somebody turning up with more than was asked for
    is a good day, and refusing to record it would mean the log stopped
    describing what happened in order to keep a number tidy.
    """
    from .models import MaterialGiven

    quantity = Decimal(str(quantity))
    if quantity <= 0:
        raise ValueError("Record an amount greater than zero.")

    return MaterialGiven.objects.create(
        organization_id=need.organization_id, need=need, member=member,
        quantity=quantity, note=note or "", manifest=manifest)


def send_material_to_need(*, line, need, quantity, member, note=""):
    """Ship from a warehouse straight onto a project's bill of materials.

    The payoff of having both: the manifest and the project tell one story
    instead of two, and the receipt QR still proves the goods moved. Neither
    record gains a value by being joined to the other.
    """
    manifest = send_material(
        line=line, quantity=quantity, member=member,
        destination=f"{need.project.name} — {need.description[:120]}")
    record_material(need=need, member=member, quantity=quantity,
                    note=note, manifest=manifest)
    return manifest
