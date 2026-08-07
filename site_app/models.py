from django.db import models


class Attestation(models.Model):
    """One run of the policy manifest, chained to the run before it.

    Stored in this database rather than written to a file in the repository:
    a scheduled job that writes a git-tracked artifact loses its output on every
    tree clean, and the schedule keeps reporting healthy while the artifact
    quietly freezes.

    Immutability here is tamper-EVIDENCE, not permanence. Rewriting a row breaks
    every hash after it, which is what an auditor actually wants — the ability to
    see that history was altered, rather than a guarantee that a mistake can
    never be corrected.
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
