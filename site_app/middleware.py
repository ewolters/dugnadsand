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
EXEMPT_PREFIXES = ("/password/", "/logout/", "/static/", "/attestation/")


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
