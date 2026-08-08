"""Second factor, and the federation SSO relying-party endpoint.

TOTP enrollment and verification come from kjerne_platform.mfa, which is shared
across the fleet: one `mfa_totp` table keyed by email, secrets Fernet-encrypted
at rest. Sites gate their own login on is_enrolled()/verify(); dugnadsand does
it in middleware so a route added later cannot forget.
"""

import logging
import os
import time
from urllib.parse import quote

from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from kjerne_platform import federation_sso, mfa

logger = logging.getLogger(__name__)

SESSION_FLAG = "mfa_ok"
ISSUER = "Dugnadsand"


@login_required
def mfa_setup(request):
    """Show a QR to scan, then confirm it with the first code.

    Enrollment is keyed by the account's email address, so an account without
    one cannot enroll. add_member requires an email for exactly this reason.
    """
    email = (request.user.email or "").strip().lower()
    if not email:
        return render(request, "site_app/mfa_setup.html", {"no_email": True})

    if mfa.is_enrolled(email):
        return redirect("/mfa/")

    error = None
    if request.method == "POST":
        code = (request.POST.get("code") or "").strip()
        if mfa.confirm(email, code):
            request.session[SESSION_FLAG] = True
            return redirect("/offerings/")
        error = "That code did not match. Codes change every 30 seconds — try the next one."

    secret_uri = mfa.enroll(email, issuer=ISSUER)
    return render(request, "site_app/mfa_setup.html", {
        "uri": secret_uri,
        "uri_qr": f"otpauth://{quote(str(secret_uri), safe='')}",
        "error": error,
    })


@login_required
def mfa_challenge(request):
    """Ask for a code. Reached on every sign-in once enrolled."""
    email = (request.user.email or "").strip().lower()
    if not email or not mfa.is_enrolled(email):
        return redirect("/mfa/setup/")

    error = None
    if request.method == "POST":
        code = (request.POST.get("code") or "").strip()
        if mfa.verify(email, code):
            request.session[SESSION_FLAG] = True
            return redirect(request.GET.get("next") or "/offerings/")
        # Deliberately vague: a distinct message for "wrong code" versus
        # "replayed code" would tell an attacker which they had.
        error = "That code did not match."
        logger.warning("MFA challenge failed for %s", email)

    return render(request, "site_app/mfa_challenge.html", {"error": error})


# --------------------------------------------------------------------------
# Federation SSO — relying party
#
# vault authenticates a federation operator and redirects here with a signed,
# short-lived assertion. We verify it and sign the person in.
#
# What this deliberately does NOT do is grant membership. A federation operator
# arriving here has a Django login and no Member row, so every member route
# returns "Not a member of any organization" and row-level security shows them
# nothing. Mapping federation identities onto an organization's membership is
# unresolved, and guessing at it would put an outsider inside a community's
# ledger — so the answer is the fail-closed one until somebody decides.
# --------------------------------------------------------------------------

# verify_token calls .add() on this, so it must be a set. Tokens are
# short-lived, so a process-local replay guard is enough — but the process is
# long-lived, so it is capped rather than left to grow for the life of a worker.
_seen_jti = set()
_JTI_CAP = 4096


def _prune_jti():
    if len(_seen_jti) > _JTI_CAP:
        _seen_jti.clear()


@csrf_exempt
def sso_entry(request):
    secret = os.environ.get("DUGNADSAND_SSO_SECRET")
    if not secret:
        logger.error("DUGNADSAND_SSO_SECRET is unset; refusing SSO.")
        return HttpResponseBadRequest("SSO is not configured.")

    token = request.GET.get("token") or request.POST.get("token") or ""
    if not token:
        return HttpResponseBadRequest("Missing token.")

    now = int(time.time())
    _prune_jti()
    try:
        assertion = federation_sso.verify_token(
            token, secrets={"vault": secret}, now=now, seen_jti=_seen_jti)
    except federation_sso.InvalidToken as exc:
        logger.warning("Rejected SSO token: %s", exc)
        return HttpResponseBadRequest("That sign-in link is not valid.")

    email = (assertion.email or "").strip().lower()
    if not email:
        return HttpResponseBadRequest("Assertion carried no email.")

    user, created = User.objects.get_or_create(
        username=email, defaults={"email": email})
    if not created and user.email != email:
        user.email = email
        user.save(update_fields=["email"])

    auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    logger.info("SSO sign-in for %s (new=%s)", email, created)
    return redirect("/offerings/")
