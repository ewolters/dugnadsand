"""Adding members, from the shell or from the web.

One implementation, two callers: the `add_member` command and the organizer's
web form. A second copy of this logic would drift, and the drift would be in
who is allowed to create a login.
"""

import secrets

from django.contrib.auth.models import User
from django.db import transaction

from .models import Member
from .tenancy import tenant_context


class MemberExists(ValueError):
    """That username is taken."""


def create_member(*, organization, username, display_name, email, is_organizer=False):
    """Create a login and a membership. Returns (member, one_time_password).

    The password is generated here and returned once. It is never stored in
    readable form and never emailed — whoever is adding the member is talking
    to them, and `must_change_password` makes sure it stops working as soon as
    the member picks their own.
    """
    username = username.strip()
    if not username:
        raise ValueError("A username is required.")
    # kjerne_platform.mfa keys enrollment by email address, so an account
    # without one can never gain a second factor. Requiring it here keeps that
    # from being discovered at the member's first sign-in.
    if not email.strip():
        raise ValueError("An email address is required — the second factor is keyed by it.")
    if User.objects.filter(username=username).exists():
        raise MemberExists(f"A user named '{username}' already exists.")

    password = secrets.token_urlsafe(12)

    with transaction.atomic():
        user = User.objects.create_user(
            username=username, email=email.strip(), password=password)
        with tenant_context(organization):
            member = Member.objects.create(
                organization=organization,
                user=user,
                display_name=display_name.strip(),
                is_organizer=is_organizer,
                must_change_password=True,
            )

    return member, password
