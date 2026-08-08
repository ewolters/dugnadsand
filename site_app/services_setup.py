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
