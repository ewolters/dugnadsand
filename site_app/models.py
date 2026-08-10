import uuid

from django.conf import settings
from django.db import models


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

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


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
    KINDS = [(OFFER, "Offering"), (NEED, "Need")]

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

    class Meta:
        ordering = ("-sent_at",)

    @property
    def received(self):
        return self.received_at is not None

    def __str__(self):
        return f"{self.quantity} {self.stock_line.unit} to {self.destination[:40]}"
