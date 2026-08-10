"""A mark for a person: generated, abstract, and deliberately not a face.

NO PHOTOGRAPHS, AND NOT MERELY FOR CONVENIENCE. Uploads would bring storage,
a moderation queue, EXIF stripping and an image decoder pointed at untrusted
bytes — all real, all avoidable. The argument that actually decides it is the
system's own: this is built so nobody can be ranked by what they have given,
and faces reintroduce judgement through a channel no invariant covers. There
is no test for "people were kinder to the person in the nice photograph." A
generated mark carries identity without carrying appearance.

DETERMINISTIC FROM THE MEMBER ID. The same person is the same mark on every
page and after every deploy, with nothing stored but a colour preference. The
id is a UUID and never leaves the tenant, so the mark reveals nothing a reader
did not already have.

The grid is mirrored, which is what makes an arrangement of squares read as a
thing rather than as noise — the same reason GitHub's does it. Five columns
from three columns of data.

Colour comes from CSS custom properties rather than literals, so brand-lint
still governs every value on the page and a palette change reaches these
without regenerating anything.
"""

import hashlib

from django.utils.safestring import mark_safe

# The six a member may choose between. Non-semantic on purpose: ok, warn and
# alert carry meaning elsewhere in this interface, and an avatar wearing one
# would quietly make its owner look like a status.
PALETTE = ("spruce", "ochre", "moss", "slate", "heather", "rust")

SIZE = 5          # cells across, mirrored about the centre column
CELL = 12         # user units per cell; the viewBox scales to any rendered size

# How many of the fifteen source positions fill — a band, not a probability.
# The floor exists because a sparse mark reads as noise rather than as anybody;
# the ceiling because a near-solid one reads as a smudge. Of 15 positions,
# mirroring makes 9 render as 15 cells and 12 as 20 of the 25.
FEWEST = 9
MOST = 12


def _digest(member_id):
    return hashlib.sha256(str(member_id).encode()).digest()


def colour_of(member):
    """This member's colour: their choice, or one derived from their id.

    Derived by default so a room of people looks like a room of people before
    anybody has touched a setting. Choosing is a preference, not a chore.
    """
    chosen = (getattr(member, "avatar_colour", "") or "").strip()
    if chosen in PALETTE:
        return chosen
    return PALETTE[_digest(member.id)[0] % len(PALETTE)]


def cells(member_id):
    """Which cells are filled, and which of the two weights each carries.

    Yields (column, row, heavy). Only the left half and the centre column come
    from the digest; the right half mirrors them.

    The lighter weight is .62 rather than something subtler because these are
    drawn at 22px beside a name far more often than at 96px on their own, and
    at that size a delicate second tone simply disappears.

    HOW MANY CELLS IS DECIDED FIRST, then which. Deciding per cell — a coin
    flip, or a threshold on a byte — gives a distribution rather than a bound,
    so however the probability is tuned some ids still land on four scattered
    squares and others on a solid block. Both fail: one reads as noise, the
    other as a smudge, and neither reads as a particular person.

    So a count is drawn from the digest and clamped to a band, and the cells
    with the highest scores fill. Same determinism, same variety, consistent
    visual weight across the whole set — which is most of what makes a group
    of generated marks look designed rather than merely random.
    """
    digest = _digest(member_id)
    half = SIZE // 2 + 1
    positions = [(column, row) for column in range(half) for row in range(SIZE)]

    # Score every position, then take the densest `count` of them. Index breaks
    # ties so the ordering is total and stable across Python versions.
    scored = sorted(
        ((digest[(c * SIZE + r) % len(digest)], i, c, r)
         for i, (c, r) in enumerate(positions)),
        key=lambda s: (-s[0], s[1]))

    span = MOST - FEWEST + 1
    count = FEWEST + (digest[-1] % span)

    for byte, _index, column, row in scored[:count]:
        heavy = bool(byte & 2)
        yield column, row, heavy
        if column < SIZE - 1 - column:        # mirror, never the centre twice
            yield SIZE - 1 - column, row, heavy


def svg(member, size=32, colour=None):
    """The mark as inline SVG. No user text goes into it, at any point.

    Inline rather than an <img> to a generated endpoint: the mark is cheap to
    compute, and a separate request per avatar would put a member id in an
    access log for every row on a page.

    `colour` overrides the member's own, for the picker — where seeing your own
    mark in each colour is the entire question a swatch of paint cannot answer.
    Anything not in PALETTE falls back, so nothing a caller invents reaches the
    class attribute.
    """
    extent = SIZE * CELL
    name = colour if colour in PALETTE else colour_of(member)
    parts = [
        f'<svg class="avatar av-{name}" width="{int(size)}" '
        f'height="{int(size)}" viewBox="0 0 {extent} {extent}" '
        f'role="img" aria-hidden="true" focusable="false">'
    ]
    for column, row, heavy in cells(member.id):
        parts.append(
            f'<rect x="{column * CELL}" y="{row * CELL}" '
            f'width="{CELL}" height="{CELL}" rx="2" '
            f'fill="currentColor" opacity="{"1" if heavy else ".62"}"/>')
    parts.append("</svg>")
    # Every value above is an integer this module computed or a constant it
    # owns. Nothing a member typed appears anywhere in the output.
    return mark_safe("".join(parts))
