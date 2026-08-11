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

import logging
from datetime import datetime, timezone

from .models import Application, Credential, Screening

logger = logging.getLogger(__name__)
SITE = "dugnadsand"


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


# --------------------------------------------------------------------------
# Telling people. Deliberately NOT called from submit(), admit() or decline():
# those are the record, and a mail outage must not roll back an application
# somebody has already filled in. The view and the command call these after
# the write has landed, and every failure here is logged and swallowed.
# --------------------------------------------------------------------------


def _mail(*, to, subject, body):
    from kjerne_platform import email

    try:
        return email.send(to=to, subject=subject, body=body, site=SITE,
                          from_name="Dugnadsand")
    except Exception:
        # An application that is recorded but unacknowledged is recoverable.
        # An application lost because the mail queue was down is not.
        logger.exception("could not send %r for an application", subject)
        return None


def acknowledge(application):
    """Tell the applicant it arrived, and what happens next.

    Does not quote their own statement back at them. They wrote it; repeating
    it puts a copy in a mailbox for no benefit, and the same paragraph would
    then exist in two places with different retention.
    """
    owed = ", ".join(c.kind for c in application.credentials.all())
    checks = (f"\nWhat will be checked against whoever issued it:\n  {owed}\n"
              if owed else "")
    if application.kind == Application.INDIVIDUAL:
        checks = ("\nA search of the public registries this chapter checks "
                  "will be run and recorded by a person.\n")

    return _mail(
        to=application.email,
        subject="Your application to Dugnadsand",
        body=(
            f"Your application was received on "
            f"{application.submitted_at:%d %B %Y}.\n\n"
            "It records a request. Nothing has been admitted, and no account "
            "has been created.\n"
            f"{checks}\n"
            "A credential that has run out is treated as absent. The decision "
            "is made by a person and comes back to this address.\n\n"
            "If something was entered wrongly, reply to this message rather "
            "than applying again — two records for one applicant slow the "
            "review down.\n\n"
            "The statement of operating policy is at "
            "https://dugnadsand.org/policy/\n"),
    )


def tell_the_reviewer(application, *, inbox):
    """Say that one arrived. NOT what is in it.

    The same rule notifications inside the app follow: the existence of a
    record and a way to reach it, never its content. The reviewer has the
    database; an inbox does not need a second copy of somebody's tax number.
    """
    if not inbox:
        return None
    return _mail(
        to=inbox,
        subject=f"Application received: {application.get_kind_display()}",
        body=("An application was submitted.\n\n"
              f"  kind  {application.kind}\n"
              f"  id    {application.id}\n\n"
              "Nothing about the applicant is repeated here. To see it:\n"
              "  manage.py list_applications\n"),
    )


def tell_decision(application):
    """The outcome.

    A decline carries no reason. decision_note is written for the review, not
    for the applicant, and forwarding it would publish an internal note
    somebody wrote in shorthand. The contact route is given instead, so a
    person who wants to know can ask and be answered by a person.
    """
    if application.admitted is None:
        return None

    if application.admitted:
        body = (
            "Your application to Dugnadsand has been accepted.\n\n"
            "Somebody will be in touch to set up the account. Until then "
            "there is nothing to sign into.\n\n"
            "The statement of operating policy, which this agreed to, is at "
            "https://dugnadsand.org/policy/\n")
        subject = "Your application to Dugnadsand"
    else:
        body = (
            "Your application to Dugnadsand has not been taken forward.\n\n"
            "This is not a judgement about the work anybody does. If it would "
            "help to know more, reply to this message and a person will "
            "answer.\n")
        subject = "Your application to Dugnadsand"

    return _mail(to=application.email, subject=subject, body=body)


# --------------------------------------------------------------------------
# Turning a yes into a working front door.
#
# Admission used to end with a printed instruction to run three more commands,
# which meant an accepted applicant sat waiting while somebody remembered.
# This does the whole thing: the tenant, its first member, and the single-use
# link that lets that person choose their own password.
# --------------------------------------------------------------------------

class AdmissionProblem(Exception):
    """Admission cannot be completed as asked."""


def _username_for(application):
    """A login name derived from the email, then the contact name.

    Derived rather than asked for because the applicant never chose one, and
    inventing a prompt for it would put a decision in front of whoever is
    reviewing at the moment they are least able to answer it. Collisions get a
    numeric suffix; the member can be told what theirs is by the setup mail,
    which prints it.
    """
    from django.contrib.auth.models import User
    from django.utils.text import slugify

    stem = slugify((application.email or "").split("@")[0]) \
        or slugify(application.contact_name) or "member"
    stem = stem[:24]

    candidate, n = stem, 1
    while User.objects.filter(username=candidate).exists():
        n += 1
        candidate = f"{stem}-{n}"
    return candidate


def admit_to_network(*, application, user, note="", into=None, username=None):
    """Say yes, and build what the yes implies.

    business, nonprofit  a new organization, its first member, a setup link
    individual           a member of an EXISTING organization, a setup link
    chapter              a chapter, and no login

    A chapter gets no account on purpose. There is no chapter screen to sign
    into yet, and issuing a credential for a door that does not exist teaches
    somebody their password does not work.

    Refuses to run twice. The blockers are checked first, so nothing is
    created for an application that was never going to pass.
    """
    from django.db import transaction
    from django.utils.text import slugify

    from .models import Organization, Region
    from .services_members import create_member
    from .services_setup import send_setup_mail

    if application.organization_id or (application.admitted and application.decided_at):
        raise AdmissionProblem(
            "This application has already been decided. Admitting it again "
            "would create a second organization for one applicant.")

    if application.blockers:
        raise NotReady(application.blockers)

    if application.kind == Application.INDIVIDUAL and into is None:
        raise AdmissionProblem(
            "An individual joins an organization that already exists. Name it "
            "with --into <slug>; a person admitted into nothing can see "
            "nothing, because every row is scoped to a tenant.")

    if application.kind == Application.CHAPTER:
        slug = slugify(application.legal_name)[:50]
        if Region.objects.filter(slug=slug).exists():
            raise AdmissionProblem(f"A chapter with slug '{slug}' already exists.")
        region = Region.objects.create(slug=slug, name=application.legal_name)
        admit(application=application, user=user, note=note)
        return {"region": region, "organization": None, "member": None,
                "mailed": False}

    with transaction.atomic():
        if into is not None:
            organization = into
        else:
            slug = slugify(application.legal_name)[:50]
            if Organization.objects.filter(slug=slug).exists():
                raise AdmissionProblem(
                    f"An organization with slug '{slug}' is already admitted.")
            organization = Organization.objects.create(
                slug=slug, name=application.legal_name,
                region=application.region)

        member, _password = create_member(
            organization=organization,
            username=username or _username_for(application),
            display_name=application.contact_name,
            email=application.email,
            # The first person in a new organization can add the rest. Somebody
            # has to be able to, and there is nobody else yet. An individual
            # joining an existing organization gets no such privilege.
            is_organizer=into is None)

        admit(application=application, user=user, note=note,
              organization=organization)

    # After the transaction. A link minted inside it would survive a rollback
    # in the mail queue's memory while vanishing from the database.
    mailed = send_setup_mail(member) is not None

    return {"region": None, "organization": organization, "member": member,
            "mailed": mailed}
