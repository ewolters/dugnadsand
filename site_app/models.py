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
    kind = models.CharField(max_length=8, choices=KINDS, default=OFFER)
    description = models.TextField()
    hours_cap = models.PositiveIntegerField(null=True, blank=True)
    open = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    @property
    def is_need(self):
        return self.kind == self.NEED

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
