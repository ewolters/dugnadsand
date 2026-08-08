"""Force a new member to replace the password they were handed.

`add_member` generates a password, prints it once, and somebody reads it aloud.
Until the member replaces it, the person who added them can sign in as them —
so this is a redirect, not a suggestion.

Runs after TenantMiddleware: reading request.user.member needs a tenant bound,
because Member is behind row-level security.
"""

from django.shortcuts import redirect

CHANGE_URL = "/password/"

# Reachable while a change is outstanding. Everything else redirects.
#
# "/mfa/" is here to break a deadlock. A brand-new member owes both gates: the
# MFA gate sends them to /mfa/setup/, and without this entry the password gate
# sent them straight back to /password/, which the MFA gate then bounced to
# /mfa/setup/ again. Neither middleware was wrong alone; the loop existed only
# in the pair, and only on a first sign-in — which is every real one.
EXEMPT_PREFIXES = ("/password/", "/logout/", "/static/", "/attestation/",
                   "/mfa/", "/setup/")

# Reachable before a second factor has been presented. Narrower than the set
# above: a member mid-MFA has proved a password and nothing else.
MFA_EXEMPT_PREFIXES = ("/mfa/", "/logout/", "/login/", "/static/",
                       "/attestation/", "/sso/", "/setup/")


class RequireMFAMiddleware:
    """No member-facing page until a second factor has been presented.

    kjerne-services gates this inside its LoginView. Here it is middleware so a
    route added later cannot forget: the default for anything new is protected,
    and getting it wrong means adding a prefix to a list somebody reviews.

    Runs before ForcePasswordChangeMiddleware. Someone who has proved only a
    password should be sent to prove the second factor, not to choose a new
    password — the password page changes a credential and should itself be
    behind the full sign-in.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from .auth_views import SESSION_FLAG

        user = getattr(request, "user", None)
        if (user is not None and user.is_authenticated
                and not request.session.get(SESSION_FLAG)
                and not request.path.startswith(MFA_EXEMPT_PREFIXES)):
            from kjerne_platform import mfa

            email = (user.email or "").strip().lower()
            # No email means no enrollment is possible; setup explains that
            # rather than looping the person through a challenge they cannot pass.
            if not email or not mfa.is_enrolled(email):
                return redirect("/mfa/setup/")
            return redirect("/mfa/")

        return self.get_response(request)


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            if not request.path.startswith(EXEMPT_PREFIXES):
                member = getattr(user, "member", None)
                if member is not None and member.must_change_password:
                    return redirect(CHANGE_URL)
        return self.get_response(request)
