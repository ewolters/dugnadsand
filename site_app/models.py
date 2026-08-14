import re
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from kjerne_platform.crypto import EncryptedCharField, EncryptedTextField


class Organization(models.Model):
    """A vetted mutual aid organization. This is the tenant.

    Admission is a formal process run by people, not a signup form — the row is
    created once an organization has been vetted. Everything else in this file
    is scoped to one of these, and Postgres row-level security enforces that
    scoping rather than trusting application code to remember the filter.

    Not itself tenant-scoped: it IS the tenant.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=200)

    admitted_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)

    # PUBLISHED, and only if the organization fills it in. Somebody who needs
    # help does not join anything and does not post here — they contact a
    # group directly, and this is the only way to do that. Blank means the
    # organization is not listed at all, which is the direction to fail in:
    # publishing a way to reach people is a decision they make, not a default
    # they discover.
    # WHAT KIND OF PARTY THIS IS, and the reason it has to be stored rather
    # than inferred: only a vetted mutual aid group may take up a request
    # from somebody who needs help, and "vetted" has to be a fact about the
    # row. The Application that admitted an organization knows its kind, but
    # organizations admitted before the ingress existed have no application
    # at all, so the answer cannot be recovered by joining.
    AID_GROUP = "aid"
    BUSINESS = "business"
    HOUSEHOLD = "household"
    KINDS = [
        (AID_GROUP, "Mutual aid group"),
        (BUSINESS, "Business"),
        (HOUSEHOLD, "Household"),
    ]
    kind = models.CharField(max_length=12, choices=KINDS, default=HOUSEHOLD)

    public_contact = models.TextField(blank=True)

    # What they do and who they serve, in their own words. Free text for the
    # same reason every description here is: a shipped vocabulary of service
    # types would make two groups comparable, and this is not a directory of
    # vendors.
    serves = models.TextField(blank=True)

    # Which chapter admitted it. The ONLY link between a chapter and a tenant,
    # and it points this way on purpose: a label on the tenant root, rather
    # than a collection the chapter can walk into. Null for an organization
    # admitted before chapters existed, or admitted directly.
    region = models.ForeignKey(
        "Region", on_delete=models.PROTECT, null=True, blank=True,
        related_name="organizations")

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    @property
    def is_aid_group(self):
        """Whether this organization may take up a request.

        Defaults to False for anything not explicitly marked, because the
        default has to be the safe one: a household or a business reaching
        somebody who asked for help is the failure this gate exists to
        prevent.
        """
        return self.kind == self.AID_GROUP

    # What counts as a licence to practise. Deliberately not a shipped list of
    # trades -- "Electrical contractor", "Journeyman electrician" and "Master
    # electrician" are three different documents in one state and named
    # differently in the next. The kind is free text an officer typed while
    # looking at the document, so this matches the shape of the words instead.
    LICENCE_WORDS = re.compile(r"licen[cs]e|certificat(?:e|ion)|registration"
                               r"|permit|credential", re.I)

    def licences(self):
        """Licences this organization DECLARED when it applied.

        Declared, not verified, and deliberately not date-checked. Both of
        those used to be true and both were wrong, in opposite directions.

        Verified was wrong because filtering on verified_on made the sentence
        somebody ticks depend on OUR check, which turns their statement into
        our representation. It is their licence and their claim to make.

        Date-checking was worse, and was a live defect: an expired credential
        dropped out of this list, so no affirmation was asked at all and the
        posting went up looking exactly like one from somebody who had never
        held a licence. An expiry made the system ask for LESS. It now asks
        the same question either way, and the sentence they agree to is that
        the licence is current -- which is a thing they know and we do not.
        """
        return [c for application in self.applications.all()
                for c in application.credentials.all()
                if self.LICENCE_WORDS.search(c.kind or "")]


class TenantScoped(models.Model):
    """Everything a member touches belongs to exactly one organization."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="%(class)ss"
    )

    class Meta:
        abstract = True


class Member(TenantScoped):
    """A person in an organization.

    Deliberately absent: any stored total, standing, tier, or rating. A member
    row says who someone is. It never says what they are worth or what they are
    entitled to — see policy/manifest.toml, no-balance.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="member",
    )
    display_name = models.CharField(max_length=120)
    joined_at = models.DateTimeField(auto_now_add=True)

    # Organizers can add other members. That is the whole privilege — they get
    # no extra visibility into the ledger and no say over who may claim what,
    # because there is nothing to have a say over.
    # A colour name from site_app.avatars.PALETTE, or blank for one derived
    # from the id. Deliberately NOT choices= on the field: a choices edit needs
    # a migration, and the palette is a design decision that should not need
    # one. The form validates against PALETTE, and anything unrecognised falls
    # back to the derived colour rather than rendering nothing.
    avatar_colour = models.CharField(max_length=20, blank=True)

    is_organizer = models.BooleanField(default=False)

    # New members arrive with a password somebody else typed and read aloud.
    # Until they replace it, the person who added them can sign in as them.
    must_change_password = models.BooleanField(default=False)

    class Meta:
        ordering = ("display_name",)

    def __str__(self):
        return self.display_name


class Project(TenantScoped):
    """Something ongoing that people give time to. A container, and nothing more.

    Every other project model in this federation is accountability machinery,
    and that is the right design where it lives. hoshined's Project carries
    benefit_type (Operational/Capex Savings), gl_account, financial_category,
    assurance, needs_approval and approved_by, because it exists to prove a
    saving to a plant controller. svend's ActionItem carries owner_name, a
    status running to Completed and Blocked, due_date, progress and depends_on,
    because it exists to run a Gantt chart.

    Both answer "who owes what by when, and what was it worth". This system is
    built so that question cannot be asked, so none of those fields may appear
    here:

      owner / owner_name  — assignment is obligation (no-obligation)
      status / progress   — recording a completion is recording a duty owed
      benefit / savings   — valuation (flat-hours, no-tax-artifact)
      needs_approval      — a gate, and gates are what this system removes
      depends_on          — a dependency is a promise somebody else is holding

    What is left is a name, a description in somebody's own words, and whether
    it is still going. Postings hang off it; hours are recorded against those
    postings and are readable as a log, never summed into a figure for the
    project or for any person in it — see no-aggregate-display.
    """

    name = models.CharField(max_length=200)
    description = models.TextField()

    # Who wrote it down. Not who is responsible for it — nobody is, and there
    # is deliberately no field that could be read as saying otherwise.
    started_by = models.ForeignKey(
        Member, on_delete=models.PROTECT, related_name="projects_started")

    open = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.name


class Posting(TenantScoped):
    """Something on the board, in either direction.

    An OFFER is something a member is putting up — produce, an afternoon, a
    spare ladder. A NEED is something a member is asking for. Both are the same
    shape, which is why they are one model: free text, a rough size, open or
    closed.

    The roles flip between them, and that is why a Claim means "I am the one on
    this" rather than "I am taking this". On an offer the poster gives and the
    claimer receives; on a need the poster receives and the claimer gives.

    Asking must cost nothing and prove nothing. Nothing here, and nothing in
    the views that read it, may consult what the poster has contributed — see
    policy/manifest.toml, no-gating.

    `description` is free text on purpose. A category list would create
    comparables, comparables create ascertainable value, and a suggested-hours
    hint is a price list wearing a helper's hat — see no-catalog.

    `hours_cap` is a ceiling and never a floor. Offering four hours means up to
    four, never at least four; nothing records stopping early — see
    no-obligation.
    """

    OFFER = "offer"
    NEED = "need"
    # Neither. Somebody saying hello, that the food bank is shut on Monday,
    # or thank you for Saturday. A community that can only ask and offer is a
    # transaction desk with a nice tone of voice.
    #
    # kind stays the ONE field on this model carrying a vocabulary, and it is
    # still a direction rather than a description of the work — no-catalog is
    # about what the help IS, and "note" says nothing about that.
    NOTE = "note"
    KINDS = [(OFFER, "Offering"), (NEED, "Need"), (NOTE, "Just saying")]

    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="postings")

    # Optional throughout. A posting that belongs to nothing is the normal
    # case, and a project is only ever a place to gather related ones — never
    # a requirement, an approval step, or somewhere a posting must be filed.
    project = models.ForeignKey(
        "Project", on_delete=models.PROTECT, null=True, blank=True,
        related_name="postings")

    kind = models.CharField(max_length=8, choices=KINDS, default=OFFER)
    description = models.TextField()
    hours_cap = models.PositiveIntegerField(null=True, blank=True)

    # WHAT SOMEBODY AGREED TO WHEN THEY OFFERED, snapshotted as text.
    #
    # An electrician offering an evening on this board is offering it as an
    # electrician. This records that they said so, and names the licence they
    # said it under, at the moment they said it -- a snapshot rather than a
    # link, because a licence later renewed, lapsed or corrected must not
    # rewrite what somebody agreed to in March.
    #
    # Blank for everybody holding no licence, which is most people. It is not
    # a rank and nothing sorts by it: an offer of a licensed trade and an
    # offer of an afternoon sit in the same feed in the same order.
    offered_under = models.CharField(max_length=200, blank=True)

    # When it stops being useful. A ride on Thursday and a fence sometime this
    # year are different problems, and until this existed the board could not
    # tell them apart — everything was equally urgent, which is to say nothing
    # was. Optional: plenty of help has no deadline.
    needed_by = models.DateField(null=True, blank=True)

    open = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    @property
    def is_need(self):
        return self.kind == self.NEED

    @property
    def is_note(self):
        """Nothing to take up. There is no claim, no hours and no deadline —
        the whole point is that it asks nothing of anybody."""
        return self.kind == self.NOTE

    @property
    def days_left(self):
        """Whole days until this stops being useful, or None if open-ended."""
        if not self.needed_by:
            return None
        from django.utils import timezone
        return (self.needed_by - timezone.localdate()).days

    @property
    def urgency(self):
        """A word for how soon, for people rather than for sorting.

        Deliberately about the POSTING and never about the person who made it.
        The moment a board ranks by who posted rather than by what is needed,
        it has started gating — see policy/manifest.toml, no-gating.
        """
        days = self.days_left
        if days is None:
            return "whenever"
        if days < 0:
            return "overdue"
        if days == 0:
            return "today"
        if days == 1:
            return "tomorrow"
        if days <= 7:
            return f"in {days} days"
        return "later"

    def __str__(self):
        return f"{self.get_kind_display()}: {self.description[:50]}"


class Claim(TenantScoped):
    """Somebody is the one on this posting.

    On an offer that means they are taking it. On a need it means they are
    doing it. One word for both, because the record does not care which
    direction the help ran.

    Note what is absent, because the absence is the design: no amount, no
    counterparty balance, no settlement, and no link to any contribution. Taking
    costs nothing and moves nothing, and claiming never consults what the
    claimant has given — see no-gating and no-exchange.
    """

    posting = models.ForeignKey(Posting, on_delete=models.PROTECT, related_name="claims")
    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="claims")
    claimed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-claimed_at",)

    def __str__(self):
        return f"{self.member} is on {self.posting}"


class Contribution(TenantScoped):
    """Hours that were actually given, attached to the posting they went into.

    There is no balance anywhere for these to accumulate into. An hour is one
    hour from anyone, never weighted by skill and never denominated in money —
    see flat-hours. The record describes work that happened; nobody holds it and
    nobody can spend it.

    Chained for tamper-evidence, not permanence: rewriting an entry breaks every
    hash after it, which is what lets a community show its history was not
    quietly rewritten — while still being able to correct an honest mistake.
    """

    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="contributions")
    posting = models.ForeignKey(Posting, on_delete=models.PROTECT, related_name="contributions")

    hours = models.DecimalField(max_digits=6, decimal_places=2)
    note = models.TextField(blank=True)
    recorded_at = models.DateTimeField()

    sequence = models.PositiveIntegerField()
    previous_hash = models.CharField(max_length=64, blank=True, editable=False)
    entry_hash = models.CharField(max_length=64, unique=True, editable=False)

    class Meta:
        ordering = ("-recorded_at",)
        unique_together = (("organization", "sequence"),)

    def __str__(self):
        return f"{self.hours}h by {self.member}"


class SetupLink(models.Model):
    """A single-use invitation to choose a password.

    Not tenant-scoped, deliberately: the person following it is not signed in,
    so no tenant is bound and row-level security would hide the row we need to
    read. The member behind it is looked up under the one audited bypass.

    The token is never stored. Only its SHA-256 lands here, so a copy of this
    table is not a set of working invitations.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="setup_links")

    token_hash = models.CharField(max_length=64, unique=True, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        state = "used" if self.used_at else "open"
        return f"setup link ({state}) expiring {self.expires_at:%Y-%m-%d}"


class Attestation(models.Model):
    """One run of the policy manifest, chained to the run before it.

    Not tenant-scoped: the manifest makes claims about the codebase, which is
    the same for every organization. Deliberately outside row-level security so
    the public attestation page can be read without a tenant in context.

    Stored in this database rather than written to a file in the repository: a
    scheduled job that writes a git-tracked artifact loses its output on every
    tree clean, and the schedule keeps reporting healthy while the artifact
    quietly freezes.
    """

    sequence = models.PositiveIntegerField(unique=True)
    recorded_at = models.DateTimeField()

    # UPHELD / INCOMPLETE / BREACHED. Never UPHELD while any check could not run.
    status = models.CharField(max_length=16)

    # Names the manifest version this run tested, so editing a claim makes older
    # attestations visibly about older wording.
    manifest_hash = models.CharField(max_length=64)

    payload = models.JSONField()

    previous_hash = models.CharField(max_length=64, blank=True, editable=False)
    entry_hash = models.CharField(max_length=64, unique=True, editable=False)

    class Meta:
        ordering = ("-sequence",)

    def __str__(self):
        return f"#{self.sequence} {self.status} at {self.recorded_at:%Y-%m-%d %H:%M}Z"


# --------------------------------------------------------------------------
# The virtual warehouse
#
# Businesses and farms already hold material that somebody nearby needs. The
# bottleneck in mutual aid is materials, not willing hands, and nothing else in
# this system moves that.
#
# WE NEVER TAKE CUSTODY. The goods stay where their holder keeps them; this
# stores a location and a description and nothing else. That is not modesty, it
# is the whole legal shape: no custody means no title, and no title means no
# storage liability, no insurance obligation, and no unrelated-business
# exposure. The platform stays a DIRECTORY — which is the same posture that
# keeps hours a RECORD rather than a currency.
#
# One line runs through all of it: we prove a thing moved, we never say what it
# was worth. The moment any row here carries a dollar figure it becomes an
# appraisal of donated property, produced by a platform, about a donor — see
# no-material-valuation in policy/manifest.toml.
# --------------------------------------------------------------------------


class Warehouse(TenantScoped):
    """Somewhere a member holds material. Their place, their goods, our index.

    Deliberately absent: capacity, utilisation, cost per pallet, any field that
    would make this a warehouse management system. It is an address and the
    name of somebody to ask.
    """

    name = models.CharField(max_length=200)
    holder = models.ForeignKey(
        Member, on_delete=models.PROTECT, related_name="warehouses")

    # Free text on purpose. "Second barn, gate code 4412, Ola has the key" is
    # more useful to a person driving there than any structured address.
    address = models.TextField()
    notes = models.TextField(blank=True)

    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class StockLine(TenantScoped):
    """Something available, as its holder last confirmed it.

    confirmed_at is not metadata. A quantity with no date is a claim about the
    present tense that nobody checked, and somebody drives forty miles on it.
    Every surface that shows an amount shows how old the amount is, and
    staleness must never render as availability.
    """

    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, related_name="lines")

    # Free text, like every other description in this system. A shipped
    # taxonomy of materials would make two donations comparable, and
    # comparables have a price — see no-catalog.
    description = models.TextField()
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit = models.CharField(max_length=40)

    confirmed_at = models.DateTimeField()
    confirmed_by = models.ForeignKey(
        Member, on_delete=models.PROTECT, related_name="stock_confirmations")

    available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-confirmed_at",)

    @property
    def confirmed_days_ago(self):
        from django.utils import timezone

        return (timezone.now() - self.confirmed_at).days

    @property
    def freshness(self):
        """How much this number should be trusted, in words.

        Returns a judgement rather than a date because a date invites the
        reader to do this arithmetic themselves and most will not.
        """
        days = self.confirmed_days_ago
        if days <= 0:
            return "confirmed today"
        if days == 1:
            return "confirmed yesterday"
        if days <= 14:
            return f"confirmed {days} days ago"
        if days <= 60:
            return f"not confirmed in {days // 7} weeks"
        return "not confirmed in months"

    @property
    def stale(self):
        return self.confirmed_days_ago > 14

    def __str__(self):
        return f"{self.quantity} {self.unit}"


class Manifest(TenantScoped):
    """Material moving from a warehouse to somebody who needs it.

    The receiving half is the point. A donating business needs evidence that
    its goods reached charitable use, and this can supply that — evidence of
    TRANSFER, never a valuation. Those are different documents and only one of
    them is safe for a platform to produce.

    Receipt is confirmed by scanning the QR on the paperwork travelling with
    the goods, which is a dual-path token: the receiver very often has no
    account and should not need one.
    """

    stock_line = models.ForeignKey(
        StockLine, on_delete=models.PROTECT, related_name="manifests")
    quantity = models.DecimalField(max_digits=12, decimal_places=2)

    # Where it is going, in words. Not a member FK: material frequently goes to
    # somebody who is not in this organization, which is the normal case rather
    # than an exception to model around.
    destination = models.TextField()

    sent_by = models.ForeignKey(
        Member, on_delete=models.PROTECT, related_name="manifests_sent")
    sent_at = models.DateTimeField(auto_now_add=True)

    received_at = models.DateTimeField(null=True, blank=True)
    # Free text: whoever signed for it, however they gave their name.
    received_note = models.TextField(blank=True)

    # The receipt capability, minted once and kept. It is PRINTED and travels
    # with the goods, so it has to be stable: minting a fresh one on every
    # render left a live link behind per page view, and there is no reason for
    # a second to exist while the first still works. Reissued only once the
    # stored one is spent or expired.
    receipt_token = models.CharField(max_length=128, blank=True, editable=False)

    class Meta:
        ordering = ("-sent_at",)

    @property
    def received(self):
        return self.received_at is not None

    def __str__(self):
        return f"{self.quantity} {self.stock_line.unit} to {self.destination[:40]}"


# --------------------------------------------------------------------------
# Bills of material
#
# A big project needs things as well as hands. This lists what, so people and
# businesses can bring it — and records what arrived, in a log of its own.
#
# THE CONVERSION IS THE DANGER, NOT THE LIST. "200 board-feet became 40 hours"
# reads as bookkeeping and is an exchange rate; a rate is ascertainable value
# however it is denominated, and once material and labour are commensurable the
# gift framing is gone. So there are two logs on a project, adjacent and never
# summed, and the page says so out loud rather than leaving it to be noticed.
#
# Nothing here carries a value either — see no-material-valuation. An estimate
# of donated property is a §170 appraisal produced by a platform about a donor,
# which is the one document this system must never generate.
# --------------------------------------------------------------------------


class MaterialNeed(TenantScoped):
    """A line on a project's bill of materials: what is wanted, and how much.

    Free text like every other description here. A shipped taxonomy of
    materials would make two donations comparable, and comparables have a
    price — see no-catalog.
    """

    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, related_name="needs")

    description = models.TextField()
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit = models.CharField(max_length=40)

    added_by = models.ForeignKey(
        Member, on_delete=models.PROTECT, related_name="material_needs")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)

    @property
    def brought(self):
        """How much has arrived.

        Summed in Python rather than with Django's .aggregate(), which
        no-aggregate-display matches unconditionally. The check is blunt on
        purpose and working around it is better than loosening it — a guard
        that gets relaxed to fit a feature stops being a guard.

        This is an aggregate over the NEED, never over a person. What is
        forbidden is a figure describing what somebody has given; what is
        required here is a figure describing what the project still wants,
        because material cannot be coordinated without it.

        READ THIS INSIDE A TENANT CONTEXT. It queries when accessed, not when
        the row is loaded, so outside one row-level security hides the material
        and it reports the full amount as still needed — plausible, and wrong
        in the direction that sends somebody shopping for timber that is
        already in the barn.
        """
        return sum((g.quantity for g in self.given.all()), Decimal("0.00"))

    @property
    def remaining(self):
        left = self.quantity - self.brought
        return left if left > 0 else Decimal("0.00")

    @property
    def met(self):
        return self.remaining <= 0

    def __str__(self):
        return f"{self.quantity} {self.unit} — {self.description[:40]}"


class MaterialGiven(TenantScoped):
    """Material that actually arrived. Its own log, beside the hours log.

    Deliberately absent: any value, any hour equivalence, any link to
    Contribution. The two logs on a project are incommensurable and stay that
    way — see no-material-valuation, which fails on a relation to the hours
    ledger as readily as on a field called `value`.
    """

    need = models.ForeignKey(
        MaterialNeed, on_delete=models.PROTECT, related_name="given")
    member = models.ForeignKey(
        Member, on_delete=models.PROTECT, related_name="material_given")

    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.TextField(blank=True)

    # Set when it came out of a warehouse here, so the manifest and the project
    # tell the same story. Null is the normal case: most material is bought,
    # found or spare, and requiring a manifest would mean requiring a warehouse.
    manifest = models.ForeignKey(
        "Manifest", on_delete=models.PROTECT, null=True, blank=True,
        related_name="material_given")

    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-recorded_at",)

    def __str__(self):
        return f"{self.quantity} {self.need.unit} by {self.member}"


# --------------------------------------------------------------------------
# Talking to each other
#
# Sharing needs somewhere to say things. What it does not need is a scoreboard,
# so there is no like here and there will not be. A like count is a public
# number attached to a person's contribution, which is a score wearing a warmer
# word: once posts carry visible counts people write for the counts, and
# whoever gives quietly ranks below whoever posts well.
#
# Thanks exists instead, and it is NOT A MODEL — see services.say_thanks. It is
# sent and gone. Nothing accumulates, so nothing can be counted, not even by
# somebody with a database handle.
# --------------------------------------------------------------------------


class Comment(TenantScoped):
    """Something said about a posting or a project.

    Coordination, not performance. "I have a truck Thursday" is what this is
    for. Deliberately absent: any reaction, any count, any score, any ordering
    but time.
    """

    posting = models.ForeignKey(
        Posting, on_delete=models.PROTECT, null=True, blank=True,
        related_name="comments")
    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, null=True, blank=True,
        related_name="comments")

    member = models.ForeignKey(
        Member, on_delete=models.PROTECT, related_name="comments")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(
                # Exactly one parent. A comment attached to both would appear
                # twice and belong to neither.
                check=(models.Q(posting__isnull=False, project__isnull=True)
                       | models.Q(posting__isnull=True, project__isnull=False)),
                name="comment_has_exactly_one_parent"),
        ]

    def __str__(self):
        return f"{self.member}: {self.body[:40]}"


class Pin(TenantScoped):
    """Somebody's own bookmark. Private, and that is the whole design.

    A PUBLIC pin is editorial ranking — the like problem with an editor, where
    what gets attention is decided by whoever pins rather than by whoever needs.
    This one is visible to its owner and to nobody else, and no count of it is
    computed or shown anywhere.
    """

    member = models.ForeignKey(
        Member, on_delete=models.PROTECT, related_name="pins")
    posting = models.ForeignKey(
        Posting, on_delete=models.PROTECT, null=True, blank=True,
        related_name="pins")
    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, null=True, blank=True,
        related_name="pins")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["member", "posting"], name="one_pin_per_posting",
                condition=models.Q(posting__isnull=False)),
            models.UniqueConstraint(
                fields=["member", "project"], name="one_pin_per_project",
                condition=models.Q(project__isnull=False)),
        ]

    def __str__(self):
        return f"pin by {self.member}"


class WorkDay(TenantScoped):
    """A day's work, at a place, at a time, that people turn up to.

    A Project is a container with no date and no edge. A river cleanup is not
    that: it happens on the twelfth, at the Cedar Lane put-in, from eight until
    two, and somebody has to have asked the county first. This is the model for
    the second kind of thing.

    It records where and when, and nothing about who is expected. There is no
    attendee list, no headcount target, no confirmation that somebody said they
    would come and then did not — those are the machinery of obligation, and
    no-obligation forbids them here as it does everywhere else. People give
    time by claiming postings, exactly as they do on any other day.

    Publication is gated on clearance (see Clearance below), and that gate is
    the one place in this system where something is withheld until a condition
    is met. It is worth being exact about why it is not the gate this whole
    design exists to remove:

      no-gating is about members. It forbids the record of what a member has
      given from deciding what that member may receive. This gate never reads a
      contribution, never reads a member, and cannot: it asks whether an
      external party — a county, a landowner, an insurer — has said yes to the
      organization. That is a fact about the physical world, not authority over
      a person, and test_events.py asserts the distinction by watching the SQL.

    Project deliberately refuses a needs_approval field for the opposite
    reason: there, approval would mean somebody inside the organization signing
    off on somebody else's work. Nothing here does that.
    """

    # Optional, like Posting.project. A cleanup that belongs to no ongoing
    # project is a normal thing, not a case to model around.
    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, null=True, blank=True,
        related_name="work_days")

    name = models.CharField(max_length=200)
    description = models.TextField()

    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)

    # Free text, like Warehouse.address. "The Cedar Lane put-in, park on the
    # grass by the gate" beats any structured address for somebody driving
    # there, and a structured one would tempt a map integration that leaks the
    # location of a community's work outside the tenant.
    place = models.TextField()
    muster = models.TextField(blank=True)

    called_by = models.ForeignKey(
        Member, on_delete=models.PROTECT, related_name="work_days_called")

    # Null until it clears. Set once, and never unset by publishing again.
    published_at = models.DateTimeField(null=True, blank=True)

    # Cancelling is not a status field with a workflow. It is a timestamp and a
    # reason in somebody's words, because the only thing anybody needs to know
    # is that it is off and why.
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_because = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("starts_at",)

    def __str__(self):
        return self.name

    # -- clearance -------------------------------------------------------
    # READ THESE INSIDE A TENANT CONTEXT. They query when accessed, not when
    # the row is loaded, which is the same trap MaterialNeed.brought carries.

    @property
    def outstanding(self):
        """Clearances someone said were needed and nobody has obtained."""
        return [c for c in self.clearances.all() if c.obtained_on is None]

    @property
    def lapsed(self):
        """Obtained, then expired. A permit for last Sunday is not a permit."""
        return [c for c in self.clearances.all() if c.lapsed]

    @property
    def blockers(self):
        return self.outstanding + self.lapsed

    @property
    def clear(self):
        """Whether publication is permitted. Nothing about any member."""
        return not self.blockers

    @property
    def published(self):
        return self.published_at is not None and self.cancelled_at is None


class Clearance(TenantScoped):
    """Permission from outside to do the work at all.

    A large group in a river on a Sunday, with tents, needs somebody to have
    asked: the county, the landowner, an insurer, whoever holds the gate in the
    real world. That asking happens over the phone and by email and it gets
    forgotten, and the cost of forgetting is borne by whoever turns up.

    Modelled on MaterialNeed and MaterialGiven rather than as a checkbox: a row
    exists from the moment somebody says "we will need the county's OK", and
    carries obtained_on only once it has actually been given. So the same table
    holds both the requirement and its satisfaction, and an outstanding
    requirement is visible as a row rather than as an absence nobody notices.

    kind is free text and deliberately not choices=. A shipped taxonomy of
    permission types would be wrong within a week -- every county names things
    differently -- and it would be a catalog, which this system does not keep
    of anything else either.

    RECORDING A CLEARANCE HERE DOES NOT CREATE ONE. This is a note that
    somebody says permission was given, with a reference so it can be checked.
    It is evidence of an asking, not the permission itself, and the page says
    so where somebody might otherwise rely on it.
    """

    work_day = models.ForeignKey(
        WorkDay, on_delete=models.CASCADE, related_name="clearances")

    kind = models.CharField(max_length=120)

    # Who has to say yes. Recorded when the requirement is raised, before
    # anybody has spoken to them.
    authority = models.TextField()

    # Null while outstanding.
    obtained_on = models.DateField(null=True, blank=True)

    # A permit number, an email date, a name -- whatever makes it checkable by
    # somebody who was not on the call.
    reference = models.CharField(max_length=200, blank=True)
    note = models.TextField(blank=True)

    # Null means it does not expire, which is the common case for "the owner
    # said yes". A permit for a date does expire, and a lapsed one blocks.
    expires_on = models.DateField(null=True, blank=True)

    # ONE member link, and the manifest is why. The first version of this
    # model also carried obtained_by, and no-exchange refused it: two Member
    # FKs on one row is the shape of "A gave to B", which is the relation this
    # system does not keep. Semantically it was a false positive -- both were
    # just who did the paperwork -- but every other table here carries exactly
    # one member link, and two names on a permit invites the question of who
    # is responsible for it, which Project refuses on purpose. Who spoke to
    # the county goes in note, and reference is what makes it checkable.
    raised_by = models.ForeignKey(
        Member, on_delete=models.PROTECT, related_name="clearances_raised")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("obtained_on", "created_at")

    def __str__(self):
        return f"{self.kind} from {self.authority}"

    @property
    def obtained(self):
        return self.obtained_on is not None

    @property
    def lapsed(self):
        from django.utils import timezone

        if self.obtained_on is None or self.expires_on is None:
            return False
        return self.expires_on < timezone.localdate()


class Region(models.Model):
    """A chapter. Emphatically NOT a tenant.

    Organizations carry the rows; the chapter is what people SHARE. Members of
    every organization in a chapter see one another's offers, needs, projects,
    work days and material -- see 0022_chapter_visibility, where every policy
    admits a row belonging to any organization in the current chapter. A
    network of one- and two-person organizations that could not do that would
    be a set of separate boards.

    That visibility comes from MEMBERSHIP, and this model grants none of it.
    The rule here is structural: NOTHING IN A CHAPTER MAY POINT AT
    TENANT-SCOPED DATA. Region and RegionRole carry no ForeignKey to any
    TenantScoped model in either direction, and test_regions.py asserts both
    directions by walking the field list.

    The distinction is worth holding on to. A chapter ROLE is administrative:
    the roster, and the applications addressed to the chapter. The tempting
    version of this feature is a chapter dashboard showing how each
    organization is doing, which is the per-member total the ledger is built
    not to compute, arriving one level up. Sharing a board is not the same as
    being measured on it.

    The single link is Organization.region, a label on the tenant root saying
    which chapter admitted it.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=200)

    # Where it covers, in words. Not a bounding box or a list of counties: a
    # chapter's edge is social and gets argued about, and a structured one
    # would have to be adjudicated by whoever holds the map.
    covers = models.TextField(blank=True)
    description = models.TextField(blank=True)

    # Which counties to shade on the map, as the ids in the baked SVG:
    # "greenville,spartanburg,anderson". Comma-separated text rather than a
    # geometry column because this is a diagram of where chapters are, not a
    # survey — nothing is computed from it, and a chapter that covers half a
    # county still says the county.
    map_areas = models.TextField(blank=True)

    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    @property
    def areas(self):
        return [a.strip() for a in self.map_areas.split(",") if a.strip()]


class RegionRole(models.Model):
    """Who runs a chapter.

    Attached to a User rather than to a Member, and the distinction is the
    whole point. A Member belongs to exactly one organization, so hanging a
    chapter role off one would mean the chapter was led from inside a member
    organization, with that organization's records one join away. A User is a
    login, and a login carries no tenancy of its own.

    Holding a role here grants no read of any organization's records, and
    there is no code path by which it could: RLS keys on the tenant GUC, which
    is set from a Member, and this model has no Member.
    """

    LEAD = "lead"
    ADMIN = "admin"
    ROLES = [(LEAD, "Lead"), (ADMIN, "Administrator")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    region = models.ForeignKey(
        Region, on_delete=models.CASCADE, related_name="roles")
    user = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="region_roles")

    role = models.CharField(max_length=8, choices=ROLES, default=ADMIN)

    # What they are called locally. A chapter that wants a Steward or a
    # Convenor should not have to be told it has an Administrator.
    title = models.CharField(max_length=120, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("region__name", "role", "created_at")
        constraints = [
            models.UniqueConstraint(
                fields=["region", "user", "role"], name="one_role_per_person_per_region"),
        ]

    def __str__(self):
        return f"{self.get_role_display()} of {self.region}"


class Application(models.Model):
    """Somebody asking to join the network. Outside every tenant, necessarily.

    An applicant has no organization yet, so this cannot be TenantScoped --
    the same reason SetupLink is not. Nothing here is protected by row-level
    security; it is reachable only by whoever runs the review.

    /policy/ says there is no self-service signup, and that stays true. An
    application is a request. Admission is still a decision a person makes,
    and it is still made with a command rather than a button.

    CONTAINS PERSONAL DATA AND, FOR BUSINESSES, A TAX NUMBER. Nothing in this
    model is encrypted at rest today, which is a gap recorded rather than
    papered over: kjerne-services solved the same problem with Fernet field
    encryption and this should follow it before the first real application
    lands.
    """

    CHAPTER = "chapter"
    BUSINESS = "business"
    NONPROFIT = "nonprofit"
    INDIVIDUAL = "individual"
    KINDS = [
        (CHAPTER, "A new chapter"),
        (BUSINESS, "A business"),
        (NONPROFIT, "A not-for-profit"),
        (INDIVIDUAL, "An individual"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=12, choices=KINDS)

    # Which chapter they are applying to. Null for a chapter application, and
    # null when somebody applies before any chapter covers them.
    region = models.ForeignKey(
        Region, on_delete=models.PROTECT, null=True, blank=True,
        related_name="applications")

    # ENCRYPTED AT REST. Everything below identifies a real person or a real
    # business, and an application table is the one place in this system that
    # holds it before any relationship exists. max_length is the CIPHERTEXT
    # length, which is several times the plaintext -- the widened column is
    # not a widened field.
    #
    # NOTHING ENCRYPTED HERE MAY BE FILTERED, ORDERED OR AGGREGATED IN SQL.
    # Ciphertext does not compare, and a .filter(email=...) would silently
    # match nothing forever. kind, admitted and the timestamps stay plaintext
    # precisely because those are what the review queries on.
    legal_name = EncryptedCharField(max_length=500, blank=False)
    contact_name = EncryptedCharField(max_length=500, blank=False)
    email = EncryptedCharField(max_length=500, blank=False)
    phone = EncryptedCharField(max_length=500, blank=True)
    locality = EncryptedCharField(max_length=500, blank=True)

    # Why they want in, in their own words. Deliberately not "what do you
    # offer": an applicant proves they are legitimate, never that their help
    # is worth having.
    statement = EncryptedTextField()

    # Which version of the manifest they agreed to. Recording the version
    # rather than a bare boolean means a later change to the commitments does
    # not silently re-characterise what somebody signed up to.
    agreed_policy_version = models.CharField(max_length=40, blank=True)
    # Which version of the TERMS -- the contract at /terms/ -- was agreed.
    # Separate from the policy version because the two documents do different
    # jobs and change for different reasons. See services_applications.
    agreed_terms_version = models.CharField(max_length=40, blank=True)
    agreed_at = models.DateTimeField(null=True, blank=True)

    submitted_at = models.DateTimeField(auto_now_add=True)

    # Undecided while null. True admitted, False declined -- one nullable
    # field rather than a status with a workflow, following the house style.
    admitted = models.BooleanField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        "auth.User", on_delete=models.PROTECT, null=True, blank=True,
        related_name="application_decisions")
    decision_note = EncryptedTextField(blank=True)

    # Set when admitting created a tenant, so the two are not reconciled by
    # hand later.
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, null=True, blank=True,
        related_name="applications")

    class Meta:
        ordering = ("-submitted_at",)

    def __str__(self):
        return f"{self.get_kind_display()}: {self.legal_name}"

    @property
    def decided(self):
        return self.admitted is not None

    @property
    def outstanding(self):
        """Declared proof nobody has looked at yet.

        Shown to the deciding officer as context. NOT a blocker -- see
        blockers() for why -- and never shown to another member.
        """
        return [c for c in self.credentials.all() if not c.verified_on]

    @property
    def lapsed(self):
        return [c for c in self.credentials.all() if c.lapsed]

    @property
    def unscreened(self):
        """An individual must have been looked for before being admitted."""
        if self.kind != self.INDIVIDUAL:
            return False
        return not self.screenings.filter(clear=True).exists()

    @property
    def blockers(self):
        """What stops admission. DELIBERATELY SHORT.

        This used to refuse until every credential was verified by an officer
        and nothing had expired. That was a stronger gate and a worse idea:
        verifying a licence and recording that we checked is a REPRESENTATION
        TO EVERYBODY ELSE, and a network that vouches for its members owns
        what they do in a way a network that registers them does not.

        So verification stopped being a gate. The tools survive -- an officer
        can still look at a document and record that they did, and should,
        because a bad actor is easier to refuse before admission than to
        remove after -- but the system no longer WITHHOLDS admission until
        somebody vouches, and nothing published anywhere says it did.

        What remains is the thing that is a contract rather than a claim:
        they agreed to the policy. See docs/for-counsel.md.
        """
        reasons = []
        if not self.agreed_at:
            reasons.append("the policy has not been agreed")
        return reasons

    @property
    def ready(self):
        return not self.blockers

    @property
    def unchecked(self):
        """What nobody has looked at, for the officer deciding.

        Was `blockers` until verification stopped being a gate. It still
        belongs on the officer's screen -- a person deciding wants to know
        that nobody has opened the insurance certificate -- but it is context
        for their judgement rather than a refusal by the system, and it is
        shown to nobody else. See blockers() for why the distinction matters.
        """
        notes = [f"{c.kind} — nobody has looked at this" for c in self.outstanding]
        notes += [f"{c.kind} — the date on it passed {c.expires_on}"
                  for c in self.lapsed]
        if self.unscreened:
            notes.append("no clear screening on file")
        return notes


class Credential(models.Model):
    """Proof that an applicant is who they say they are.

    The same shape as Clearance one level up: a row exists because something
    is required, and carries verified_on only once a person has actually
    looked at it. An expired credential blocks exactly as a lapsed permit
    blocks a work day -- a licence that ran out in March is not a licence, and
    the failure nobody catches is the row that was filled in correctly two
    years ago.

    Note what is NOT proved: what the applicant offers, or how good they are
    at it. An electrician proves a licence and insurance. Nothing asks them to
    justify the value of their help, because this system does not value help.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name="credentials")

    # Free text. "Business license", "Certificate of insurance", "IRS
    # determination letter" -- named differently in every state, and a shipped
    # vocabulary would be wrong within a year.
    kind = models.CharField(max_length=120)

    # Who issued it, and the number on it. ENCRYPTED: reference holds a tax
    # identification number, which is the single most sensitive value this
    # system stores. kind above stays plaintext because decide_application
    # looks credentials up by it.
    authority = EncryptedCharField(max_length=500, blank=True)
    reference = EncryptedCharField(max_length=500, blank=True)

    issued_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)

    # Set when a person has checked it against the issuer, not when the
    # applicant typed it in.
    verified_on = models.DateField(null=True, blank=True)
    verified_by = models.ForeignKey(
        "auth.User", on_delete=models.PROTECT, null=True, blank=True,
        related_name="credentials_verified")
    note = EncryptedTextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("kind",)

    def __str__(self):
        return f"{self.kind} for {self.application.legal_name}"

    @property
    def lapsed(self):
        from django.utils import timezone

        return bool(self.expires_on and self.expires_on < timezone.localdate())


class Screening(models.Model):
    """A record that somebody looked, and what they searched.

    THIS MODEL DOES NOT SEARCH ANYTHING, AND DELIBERATELY SO. Matching a name
    against a public registry produces false positives on common names, and
    wiring an automatic match into a refusal means a person is turned away by
    a string comparison nobody reviewed. Registries also disagree, lag, and
    publish in formats that change without notice.

    So a person does the search and records what they did: which registry, on
    what date, under what name, and what they found. That is evidence, it can
    be re-checked, and it puts the judgement with somebody who can be asked
    about it afterwards.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name="screenings")

    # Which registry, in words. There is no single one, and the set differs by
    # state and by what the chapter has decided it checks.
    # source stays plaintext: it names a registry, not a person, and being
    # able to report on which registries were searched is the point.
    source = models.CharField(max_length=200)
    searched_name = EncryptedCharField(max_length=500, blank=False)
    searched_on = models.DateField()
    searched_by = models.ForeignKey(
        "auth.User", on_delete=models.PROTECT, related_name="screenings_run")

    # False means something came back that needs a person, NOT that the
    # applicant is refused. The decision stays with the reviewer.
    clear = models.BooleanField()
    note = EncryptedTextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-searched_on",)

    def __str__(self):
        return f"{self.source} on {self.searched_on}"


def _photo_path(instance, filename):
    """packets/<uuid>.<ext>. The original name is discarded on purpose.

    An uploaded filename is somebody's phone's idea of a name and frequently
    carries a date, a location or a person. It is also attacker-controlled.
    """
    import os
    import uuid as _uuid

    ext = os.path.splitext(filename or "")[1].lower()[:8]
    return f"packets/{_uuid.uuid4().hex}{ext}"


class Measure(TenantScoped):
    """Something true about the world after the work, in somebody's own words.

    This is what a project reports at the end, and it is deliberately NOT
    computed from anything. "Three point two tons of debris removed" is a fact
    a person establishes and types in; it is not a sum over the ledger.

    That distinction is the whole reason this model can exist. A per-project
    total of contributed hours looks safe, because it describes work rather
    than a person -- but a project with one contributor is that contributor's
    total, and no-aggregate-display exists to prevent exactly that number.
    A measure describes the OUTCOME, so it stays a fact about a river rather
    than about anybody who stood in it.

    unit is refused if it names money or hours; see services_packet.check_unit.
    Free text otherwise, like every other unit in this system.
    """

    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, related_name="measures")

    label = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit = models.CharField(max_length=40)
    note = models.TextField(blank=True)

    recorded_by = models.ForeignKey(
        Member, on_delete=models.PROTECT, related_name="measures_recorded")
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("recorded_at",)

    def __str__(self):
        return f"{self.label}: {self.quantity} {self.unit}"


class Photo(TenantScoped):
    """A picture of the work.

    Stored under MEDIA_ROOT, which is NOT web-served: /media/ is routed
    nowhere, and every photo is delivered by a view that decides whether the
    requester may have it. A file under a guessable URL would be public the
    moment it was uploaded, published packet or not.
    """

    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, related_name="photos")

    image = models.FileField(upload_to=_photo_path)
    caption = models.CharField(max_length=300, blank=True)

    # Declared when the photograph is added, and defaulting to TRUE on
    # purpose: assume a picture of a work party has people in it until
    # somebody says otherwise. A default of False would publish faces by
    # omission, which is the direction this must never fail in.
    depicts_people = models.BooleanField(default=True)

    added_by = models.ForeignKey(
        Member, on_delete=models.PROTECT, related_name="photos_added")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)

    def __str__(self):
        return self.caption or "photo"


class Packet(TenantScoped):
    """What a project sends back to everybody who helped.

    The consideration in this system is documented outcome, not a receipt.
    Somebody who gives a pallet of shingles gets back evidence of what the
    work achieved, with photographs -- and never a figure they could put on a
    tax return, because this system does not know what anything was worth and
    is built so it cannot learn.

    So the packet carries measures, material described and counted, photos,
    and an acknowledgement written by the organization. It carries NO value,
    NO price, and NO total of contributed hours. The page says so itself,
    where somebody might otherwise rely on it.

    Acknowledgement is prose, not a computed list of contributors. Who a
    community thanks is a human act; generating it would rank people by what
    they gave, which is the score the whole system exists without.
    """

    project = models.OneToOneField(
        Project, on_delete=models.PROTECT, related_name="packet")

    title = models.CharField(max_length=200)
    summary = models.TextField()
    acknowledgements = models.TextField(blank=True)

    # Minted when published, cleared when withdrawn. Unguessable and durable:
    # unlike a receipt link this is meant to be kept and revisited, so it is
    # not single-use -- but withdrawing publication kills the old link for
    # good rather than leaving it working quietly.
    token = models.CharField(max_length=64, blank=True, editable=False)

    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        Member, on_delete=models.PROTECT, null=True, blank=True,
        related_name="packets_published")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.title

    @property
    def published(self):
        return bool(self.published_at and self.token)


class PhotoConsent(TenantScoped):
    """A record that somebody in a photograph agreed to it being published.

    CHAINED, like contributions and attestations, and for the reason those
    are: consent is the record most worth altering after the fact. Somebody
    who published a photograph they should not have has every motive to make a
    consent row appear afterwards, or to make a withdrawal disappear. Each
    entry commits to its predecessor, so an inserted, edited or deleted record
    breaks the chain from that point on and verification says where.

    TAMPER-EVIDENT, NOT TAMPER-PROOF, and not proof that consent was given.
    This says a member recorded that a person agreed, on a date, by some
    means. It is evidence of an asking, exactly as a Clearance is — the chain
    only makes that evidence hard to rewrite quietly afterwards. A community
    must still be able to correct a mistake and honour a withdrawal, which is
    why nothing here is immutable.

    The person's name is ENCRYPTED at rest, and the chain payload carries a
    KEYED digest of it rather than the name itself. A plain hash would hand
    somebody with a stolen database the ability to confirm a guessed name
    without ever having the encryption key, which would undo the encryption
    through the back door of the integrity mechanism.
    """

    photo = models.ForeignKey(
        Photo, on_delete=models.PROTECT, related_name="consents")

    # Who is depicted, as they are known locally. Most people at a work party
    # are not members, so this is a name and not a relation.
    person = EncryptedCharField(max_length=500, blank=False)

    # Null while outstanding: the row exists from the moment somebody says a
    # person is in the picture, exactly as a Clearance exists before it is
    # obtained. An outstanding consent is a visible blocker, not an absence.
    given_on = models.DateField(null=True, blank=True)
    how = models.CharField(max_length=120, blank=True)

    # Withdrawal is a first-class event, not a delete. Somebody changing their
    # mind must leave a record that they did.
    withdrawn_on = models.DateField(null=True, blank=True)

    note = EncryptedTextField(blank=True)

    # ONE member link, as everywhere else — see Clearance. Who wrote it down,
    # never who is in it.
    recorded_by = models.ForeignKey(
        Member, on_delete=models.PROTECT, related_name="consents_recorded")
    recorded_at = models.DateTimeField()

    sequence = models.PositiveIntegerField()
    previous_hash = models.CharField(max_length=64, blank=True, editable=False)
    entry_hash = models.CharField(max_length=64, unique=True, editable=False)

    class Meta:
        ordering = ("sequence",)
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "sequence"],
                name="one_consent_sequence_per_organization"),
        ]

    def __str__(self):
        return f"consent {self.sequence}"

    @property
    def given(self):
        return bool(self.given_on) and not self.withdrawn_on

    @property
    def withdrawn(self):
        return bool(self.withdrawn_on)


class Interest(TenantScoped):
    """"I might be able to help." Softer than taking something on.

    Between keeping a posting privately and committing to it there was
    nothing, so the only public move was the whole commitment. Plenty of help
    starts as "tell me more" or "I could do a couple of hours if nobody
    nearer can", and a board with no way to say that turns every tentative
    person into a silent one.

    NAMED, NEVER COUNTED. The card says who is interested, the way it already
    says who is on it. It does not say how many, and no number appears beside
    anybody's name anywhere: a count of interest is a like, a like is a score,
    and the whole system is built without one. test_interest.py asserts the
    absence rather than trusting the template.

    hours is a CEILING and never a floor -- the same rule Posting.hours_cap
    follows. Somebody who offers four hours and gives one has given one hour;
    nothing compares the two, nothing records a shortfall, and withdrawing is
    a hard delete leaving no trace, exactly as stepping off a claim is. See
    no-obligation, whose check now scans this model too.
    """

    posting = models.ForeignKey(
        Posting, on_delete=models.CASCADE, related_name="interests")
    # ONE member link, as everywhere else -- see Clearance.
    member = models.ForeignKey(
        Member, on_delete=models.PROTECT, related_name="interests")

    # Null is the ordinary case: "I'm interested" says nothing about how long.
    hours = models.DecimalField(max_digits=6, decimal_places=2,
                                null=True, blank=True)

    # WHAT SOMEBODY AGREED TO WHEN THEY OFFERED, snapshotted as text.
    #
    # An electrician offering an evening on this board is offering it as an
    # electrician. This records that they said so, and names the licence they
    # said it under, at the moment they said it -- a snapshot rather than a
    # link, because a licence later renewed, lapsed or corrected must not
    # rewrite what somebody agreed to in March.
    #
    # Blank for everybody holding no licence, which is most people. It is not
    # a rank and nothing sorts by it: an offer of a licensed trade and an
    # offer of an afternoon sit in the same feed in the same order.
    offered_under = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(fields=["posting", "member"],
                                    name="one_interest_per_person_per_posting"),
        ]

    def __str__(self):
        return f"{self.member} is interested"


class ChapterRemoval(models.Model):
    """A record that an organization was removed from a chapter.

    Not tenant-scoped, like Region: it is about the relationship between a
    chapter and an organization rather than about anything inside either.

    The removal itself is just Organization.region going null, which the
    chapter-aware policy turns into invisibility. That is effective and it is
    also completely silent — nothing would say it happened, who did it, or
    why. The acceptable use policy calls this the strongest remedy available,
    and a strongest remedy that leaves no trace is one nobody can be asked
    about afterwards.

    Kept even if the organization is later readmitted, and never edited.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    region = models.ForeignKey(
        Region, on_delete=models.PROTECT, related_name="removals")
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="chapter_removals")

    # The officer, by login. Same reason RegionRole attaches to a User.
    removed_by = models.ForeignKey(
        "auth.User", on_delete=models.PROTECT, related_name="chapter_removals")
    reason = models.TextField()
    removed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-removed_at",)

    def __str__(self):
        return f"{self.organization} removed from {self.region}"


class Request(models.Model):
    """Somebody asked for help. Blind, and outside every tenant.

    NOT TenantScoped: the person asking belongs to no organization and never
    will. They do not join, do not register, and are never a party to this
    system — see the statement of operating policy, "Where this system stops".

    BLIND MEANS BLIND. What appears in the community is the need and a coarse
    area. The name and the way to reach them are encrypted at rest and are
    disclosed to exactly one organization: the aid group that takes it up.
    Nobody else sees them at any point, including businesses and households in
    the same chapter, and including before anybody has taken it.

    That asymmetry is the whole design. A person in trouble should not have to
    be publicly identifiable in order to be helped, and a business browsing
    the feed has no reason to learn who is struggling on which street.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Which chapter's groups can see it. Null means nobody yet — a request
    # from outside every covered area waits rather than going to everyone.
    region = models.ForeignKey(
        Region, on_delete=models.PROTECT, null=True, blank=True,
        related_name="requests")

    # Shown. Free text, written by whoever asked.
    need = models.TextField()

    # Shown, and deliberately coarse. A town, not an address: the feed says
    # where roughly, and the group that takes it learns the rest.
    area = models.CharField(max_length=120, blank=True)

    # WITHHELD until taken. Encrypted at rest like every other personal
    # detail this system holds.
    asked_by = EncryptedCharField(max_length=500, blank=True)
    reach_them = EncryptedTextField()

    created_at = models.DateTimeField(auto_now_add=True)

    # Set when an aid group takes it up. Only then does that group see the
    # contact, and only that group.
    taken_by = models.ForeignKey(
        Organization, on_delete=models.PROTECT, null=True, blank=True,
        related_name="requests_taken")
    taken_at = models.DateTimeField(null=True, blank=True)

    # Closed by the group that took it, or left alone. No outcome is
    # recorded: what happened between a group and a person is theirs, and a
    # field for it would be this system reaching into the last mile.
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"request {self.id}"

    @property
    def taken(self):
        return self.taken_by_id is not None

    @property
    def open(self):
        return self.taken_by_id is None and self.closed_at is None
