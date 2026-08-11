"""Single-use setup links.

An invitation that lets somebody choose their own password, so no working
credential ever travels by email. The token is generated once, hashed, and only
the hash is stored — a copy of the table is not a set of working invitations.
"""

import hashlib
import secrets
from datetime import timedelta

from django.utils import timezone

from .models import SetupLink
from .tenancy import bypass_rls

LIFETIME = timedelta(days=7)


class LinkUnusable(ValueError):
    """Unknown, already used, or expired."""


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def issue_setup_link(member, *, lifetime=LIFETIME):
    """Create a link for this member. Returns the raw token, once.

    Any earlier unused link for the same member is retired: a person who has
    been sent two invitations should not have two live ways in.
    """
    token = secrets.token_urlsafe(32)
    now = timezone.now()

    with bypass_rls():
        SetupLink.objects.filter(member=member, used_at__isnull=True).update(used_at=now)
        SetupLink.objects.create(
            member=member,
            token_hash=_hash(token),
            expires_at=now + lifetime,
        )
    return token


def resolve_setup_link(token):
    """Return the member this token belongs to, or raise LinkUnusable.

    Looks up by hash, so a token that is not in the table cannot be guessed at
    from what is.
    """
    if not token:
        raise LinkUnusable("No token.")

    with bypass_rls():
        link = SetupLink.objects.filter(token_hash=_hash(token)).first()
        if link is None:
            raise LinkUnusable("That link is not valid.")
        if link.used_at is not None:
            raise LinkUnusable("That link has already been used.")
        if link.expires_at <= timezone.now():
            raise LinkUnusable("That link has expired.")
        return link, link.member


def consume_setup_link(link):
    with bypass_rls():
        SetupLink.objects.filter(pk=link.pk, used_at__isnull=True).update(
            used_at=timezone.now())


# --------------------------------------------------------------------------
# The invitation mail. Extracted from the send_setup_link command so that the
# admission path and the command send the SAME letter: two copies would drift,
# and the drift would be in what a new member is told this system is.
# --------------------------------------------------------------------------

BASE_URL = "https://dugnadsand.org"
SITE = "dugnadsand"


def send_setup_mail(member):
    """Mint a single-use link and email it. Returns the queue id, or None if
    the address is suppressed.

    Minting happens here rather than in the caller because a link that is
    created and then not sent is a live credential nobody knows about.
    """
    from kjerne_platform import email as platform_email

    user = member.user
    token = issue_setup_link(member)
    link = f"{BASE_URL}/setup/{token}/"

    body = (
        f"Hello {member.display_name},\n\n"
        f"Your account for Dugnadsand is ready. Follow this link to choose a "
        f"password and set up a second factor:\n\n"
        f"    {link}\n\n"
        f"The link works once and expires in seven days. Your username is "
        f"{user.username}.\n\n"
        f"Dugnadsand writes down what happened and never what it was worth. "
        f"Hours given, material brought — kept in separate records, never added "
        f"together and never priced. None of it is a currency: nothing is bought, "
        f"sold or owed, and nothing you do or don't contribute changes what you "
        f"can ask for.\n\n"
        f"{BASE_URL}\n"
    )

    return platform_email.send(
        to=user.email, subject="Your Dugnadsand account", body=body,
        site=SITE, from_name="Dugnadsand")
