"""Getting into the network.

An applicant proves they are legitimate. They never prove that what they offer
is worth having -- there is no assessment of an electrician's work, no rating,
no tier. The distinction matters because a system that graded offers would be
pricing them, and this one prices nothing.

What is required differs by kind, and the differences are the point:

  business    a licence and insurance, both of which expire, plus a tax number
  nonprofit   a determination letter and a tax number, which do not expire
  individual  no documents at all -- an agreement and a screening somebody ran
  chapter     a conversation; nothing here can substitute for one

Admission is still a command. /policy/ tells every visitor there is no
self-service signup, and an application that admitted itself once the boxes
went green would make that false while looking like diligence.
"""

from datetime import datetime, timezone

from .models import Application, Credential, Screening


class NotReady(Exception):
    """Admission refused: something required is missing, unverified or expired."""

    def __init__(self, blockers):
        self.blockers = blockers
        super().__init__("; ".join(blockers) or "not ready")


# What each kind must produce. The booleans say whether an expiry date is
# expected, which is what makes a stale credential detectable rather than
# merely old.
REQUIRED = {
    Application.BUSINESS: [
        ("Business license", True),
        ("Certificate of insurance", True),
        ("Tax identification number", False),
    ],
    Application.NONPROFIT: [
        ("IRS determination letter", False),
        ("Tax identification number", False),
    ],
    Application.INDIVIDUAL: [],
    Application.CHAPTER: [],
}


def _now():
    return datetime.now(timezone.utc)


def policy_version():
    """The manifest version an applicant is agreeing to.

    Recorded rather than a bare yes, so that changing a commitment later does
    not silently re-characterise what somebody already signed.
    """
    from policy.attest import load_manifest

    return str(load_manifest()["manifest"].get("version", ""))


def submit(*, kind, legal_name, contact_name, email, statement, region=None,
           phone="", locality="", agreed=False, credentials=()):
    """Record an application and raise the proof it still owes.

    credentials is what the applicant typed in. Rows are created for
    everything the kind requires, whether or not the applicant supplied it, so
    an omission is a visible outstanding row rather than a silence.
    """
    application = Application.objects.create(
        kind=kind, region=region, legal_name=legal_name,
        contact_name=contact_name, email=email, phone=phone,
        locality=locality, statement=statement,
        agreed_policy_version=policy_version() if agreed else "",
        agreed_at=_now() if agreed else None)

    supplied = {k: v for k, v in (credentials or {}).items()}
    for name, _expires in REQUIRED.get(kind, []):
        given = supplied.get(name, {})
        Credential.objects.create(
            application=application, kind=name,
            authority=given.get("authority", ""),
            reference=given.get("reference", ""),
            expires_on=given.get("expires_on"))

    return application


def verify_credential(*, credential, user, verified_on, expires_on=None,
                      reference=None, note=None):
    """A person checked this against whoever issued it."""
    credential.verified_on = verified_on
    credential.verified_by = user
    if expires_on is not None:
        credential.expires_on = expires_on
    if reference is not None:
        credential.reference = reference
    if note is not None:
        credential.note = note
    credential.save(update_fields=["verified_on", "verified_by", "expires_on",
                                   "reference", "note"])
    return credential


def record_screening(*, application, user, source, searched_name, searched_on,
                     clear, note=""):
    """Record that somebody looked, where, and what came back.

    clear=False does not refuse anybody. It says a person needs to look at
    this, which is the only safe meaning for a name match.
    """
    return Screening.objects.create(
        application=application, source=source, searched_name=searched_name,
        searched_on=searched_on, searched_by=user, clear=clear, note=note)


def admit(*, application, user, note="", organization=None):
    """Say yes, or refuse and name everything that is missing."""
    if application.blockers:
        raise NotReady(application.blockers)

    application.admitted = True
    application.decided_at = _now()
    application.decided_by = user
    application.decision_note = note
    application.organization = organization
    application.save(update_fields=["admitted", "decided_at", "decided_by",
                                    "decision_note", "organization"])
    return application


def decline(*, application, user, note=""):
    """Say no. Always permitted: a refusal needs no paperwork to be complete."""
    application.admitted = False
    application.decided_at = _now()
    application.decided_by = user
    application.decision_note = note
    application.save(update_fields=["admitted", "decided_at", "decided_by",
                                    "decision_note"])
    return application
