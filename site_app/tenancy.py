"""Tenant scoping, enforced by Postgres rather than by remembering to filter.

Every tenant-scoped table carries `ENABLE` **and** `FORCE ROW LEVEL SECURITY`
with a policy keyed on `app.current_tenant_id`. Django connects as
`dugnadsand_app`, which is not the table owner, so plain ENABLE would already
bind it; FORCE is what also binds `dugnadsand_owner` when it runs migrations,
so no role gets a free pass by accident.

The important property is that it **fails closed**. With no tenant in context
the setting is NULL, no policy matches, and every query returns nothing. A view
that forgets its filter returns an empty page; it does not return another
organization's members.

`app.bypass_rls` is the one escape hatch, used by migrations and by nothing
else. Komunitin does the same thing for the same reason, and keeping it to a
single call site is what makes it auditable.
"""

from contextlib import contextmanager

from django.db import connection

TENANT_SETTING = "app.current_tenant_id"
REGION_SETTING = "app.current_region_id"
BYPASS_SETTING = "app.bypass_rls"


def set_tenant(organization_id, region_id=None):
    """Bind this connection to one organization, and to its chapter.

    TWO settings, because there are two boundaries and they are not the same.

    The organization says whose row a new record belongs to. The chapter says
    what this member can SEE — a network of one-person organizations is the
    normal case here, and requiring people to share an organization to see one
    another's board would be requiring them to share an employer.

    Either being None clears it, and clearing fails closed: with no chapter
    bound the region clause matches nothing, so an organization outside any
    chapter is isolated exactly as it was before.
    """
    with connection.cursor() as cur:
        cur.execute(
            "SELECT set_config(%s, %s, FALSE), set_config(%s, %s, FALSE)",
            [TENANT_SETTING, str(organization_id) if organization_id else "",
             REGION_SETTING, str(region_id) if region_id else ""],
        )


def current_tenant():
    with connection.cursor() as cur:
        cur.execute("SELECT current_setting(%s, TRUE)", [TENANT_SETTING])
        value = cur.fetchone()[0]
    return value or None


def current_region():
    with connection.cursor() as cur:
        cur.execute("SELECT current_setting(%s, TRUE)", [REGION_SETTING])
        value = cur.fetchone()[0]
    return value or None


@contextmanager
def tenant_context(organization):
    """Run a block scoped to one organization, restoring whatever was set before.

    Used by management commands, the ingest paths, and tests. Request handling
    goes through TenantMiddleware instead.
    """
    previous, previous_region = current_tenant(), current_region()
    organization_id = getattr(organization, "id", organization)
    # An Organization instance carries its chapter; a bare id cannot, so a
    # caller passing one gets organization-only scope. Every caller that needs
    # chapter visibility passes the object.
    region_id = getattr(organization, "region_id", None)
    set_tenant(organization_id, region_id)
    try:
        yield
    finally:
        set_tenant(previous, previous_region)


@contextmanager
def bypass_rls():
    """Escape hatch. Migrations only.

    Kept to one place on purpose: an escape hatch scattered through a codebase
    is not an escape hatch, it is the absence of row-level security.
    """
    with connection.cursor() as cur:
        cur.execute("SELECT set_config(%s, 'on', FALSE)", [BYPASS_SETTING])
    try:
        yield
    finally:
        with connection.cursor() as cur:
            cur.execute("SELECT set_config(%s, 'off', FALSE)", [BYPASS_SETTING])


class TenantMiddleware:
    """Resolve the organization for this request and bind the connection.

    Resolution is by the authenticated member. Anonymous requests get no tenant,
    which under RLS means no tenant-scoped rows are visible at all — the public
    landing page and the attestation page need none, and everything else should
    be behind a login.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _resolve(request):
        """Which organization is this request for?

        Chicken-and-egg: the answer lives in Member, and Member is behind RLS,
        which shows nothing until a tenant is bound. So the lookup that
        bootstraps the tenant is the one place that has to run privileged.

        It is kept as narrow as it can be — one row, one column, by user id —
        and it is why bypass_rls() exists as a named, single-purpose hatch
        rather than a general-purpose one. Everything after this line is scoped
        normally.
        """
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            # A PAIR, like every other return here. Returning a bare None left
            # the caller unpacking it, and an anonymous request is the most
            # common request there is.
            return (None, None)

        from .models import Member

        with bypass_rls():
            return (
                Member.objects
                # active=True is LOAD-BEARING and was not, until now. The flag
                # existed on Organization and was read in one place that gated
                # nothing, so an organization could be marked inactive while
                # every one of its members carried on exactly as before. A
                # switch that looks like a switch and is not one is worse than
                # no switch: somebody flips it and believes something happened.
                .filter(user_id=user.pk, organization__active=True)
                .values_list("organization_id", "organization__region_id")
                .first()
            ) or (None, None)

    @staticmethod
    def _closed(request):
        """True when this user belongs to an organization that is not active.

        Without this the member simply sees nothing: RLS is doing its job and
        the app is empty, which reads as broken rather than as closed. Costs
        one query and only for a signed-in user with no resolvable tenant.
        """
        from .models import Member

        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        with bypass_rls():
            return Member.objects.filter(user_id=user.pk).exists()

    def __call__(self, request):
        organization_id, region_id = self._resolve(request)
        if organization_id:
            request.organization_id = organization_id
            request.region_id = region_id

        # A member row exists but no tenant resolved: the organization is
        # inactive. Say so once rather than serving an empty application.
        if organization_id is None and self._closed(request):
            from django.shortcuts import render
            if not request.path.startswith(("/logout/", "/static/")):
                set_tenant(None, None)
                return render(request, "site_app/closed.html", status=403)

        set_tenant(organization_id, region_id)
        try:
            return self.get_response(request)
        finally:
            # Connections are pooled and reused; a tenant left bound to one
            # would leak into whoever gets the connection next.
            set_tenant(None, None)
