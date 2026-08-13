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
PENDING_URI = "mfa_pending_uri"
ISSUER = "Dugnadsand"

# Shown for every unusable setup link, whatever was actually wrong with it.
GENERIC_REFUSAL = ("This link is not usable. Setup links work once and expire "
                   "after a week.")


def _qr_svg(data, width="38mm"):
    """Render a QR as inline SVG, or None if it cannot be done honestly.

    Inline rather than an <img> to a generated endpoint: the MFA URI contains
    the shared secret, and a separate request for it would put that secret in
    a server log, a proxy cache and the browser's history. Inline SVG keeps it
    in the one response that already carries it.

    Drawn by juniper, which asks for a size in MILLIMETRES rather than pixels
    because these end up on paper — a manifest is printed and scanned in a
    barn. juniper refuses a width that would put the modules under the
    scannable minimum instead of drawing something that looks like a code and
    is not one, and that refusal is the reason to use it here.

    Degrades rather than breaks. Every caller shows the underlying value as
    text too, so somebody whose camera will not focus, or who is reading this
    over SSH, is never stuck.
    """
    try:
        from juniper.symbology import encode, render_svg

        return render_svg(encode("qr", data), width=width)
    except Exception:
        logger.warning("could not render a QR for %d bytes", len(data or ""),
                       exc_info=True)
        return None


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
            request.session.pop(PENDING_URI, None)
            request.session[SESSION_FLAG] = True
            return redirect("/board/")
        error = "That code did not match. Codes change every 30 seconds — try the next one."

    # enroll() overwrites any unconfirmed secret, so calling it on every render
    # would silently kill the code somebody had just scanned the moment they
    # refreshed, or failed a code and got this page back. Hold the pending URI
    # in the session and re-show the same one, as kjerne-services does.
    uri = request.session.get(PENDING_URI)
    if not uri:
        try:
            # enroll returns (secret, otpauth_uri) — the secret is already
            # stored, and only the URI belongs on the page.
            _secret, uri = mfa.enroll(email, issuer=ISSUER)
        except mfa.AlreadyEnrolled:
            return redirect("/mfa/")
        request.session[PENDING_URI] = uri

    return render(request, "site_app/mfa_setup.html", {
        "uri": uri,
        "qr_svg": _qr_svg(uri),
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
            return redirect(request.GET.get("next") or "/board/")
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
    return redirect("/board/")


# --------------------------------------------------------------------------
# Setup links
#
# A new member is invited rather than issued a credential: the link lets them
# choose their own password, so nothing that works travels by email. Following
# it signs them in, and the MFA gate takes over from there.
# --------------------------------------------------------------------------


@csrf_exempt
def setup(request, token):
    from django.contrib.auth.forms import SetPasswordForm
    from kjerne_platform import rate_limit

    from .services_setup import LinkUnusable, consume_setup_link, resolve_setup_link
    from .tenancy import bypass_rls

    ip = (request.META.get("HTTP_CF_CONNECTING_IP")
          or request.META.get("REMOTE_ADDR", "unknown"))
    if not rate_limit.check("dugnadsand_setup", ip, 20, 3600):
        return render(request, "site_app/setup.html",
                      {"problem": "Too many attempts. Try again later."}, status=429)

    try:
        link, member = resolve_setup_link(token)
    except LinkUnusable as exc:
        # One message for unknown, used and expired. The specific reason goes to
        # the log, not to the page: rendering "has expired" where another token
        # gets "is not valid" tells a visitor which tokens once existed.
        logger.info("Setup link refused: %s", exc)
        return render(request, "site_app/setup.html",
                      {"problem": GENERIC_REFUSAL}, status=404)

    user = member.user
    form = SetPasswordForm(user, request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        consume_setup_link(link)
        with bypass_rls():
            member.must_change_password = False
            member.save(update_fields=["must_change_password"])
        auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        # Straight into enrolling a second factor; the gate would send them
        # there anyway, and arriving on purpose reads better than a bounce.
        return redirect("/mfa/setup/")

    return render(request, "site_app/setup.html", {
        "form": form,
        "member": member,
        "username": user.username,
    })
