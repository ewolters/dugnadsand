import logging
import os
from hmac import compare_digest

from django.contrib.auth.decorators import login_required
from django.http import (HttpResponseBadRequest, HttpResponseForbidden,
                         JsonResponse)
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from kjerne_platform import email, rate_limit

from .forms import ContactForm

logger = logging.getLogger(__name__)

SITE = "dugnadsand"
# Set per deployment; deliberately absent from the repo so no inbox is published.
INBOX = os.environ.get("DUGNADSAND_CONTACT_EMAIL")


def _client_ip(request):
    forwarded = request.META.get("HTTP_CF_CONNECTING_IP") or request.META.get(
        "HTTP_X_FORWARDED_FOR", ""
    )
    return forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")


def index(request):
    if request.method != "POST":
        return render(request, "site_app/index.html", {
            "form": ContactForm(),
            "sent": request.GET.get("sent") == "1",
        })

    form = ContactForm(request.POST)
    if not form.is_valid():
        return render(request, "site_app/index.html", {"form": form, "sent": False})

    # Five a day per address keeps a bored someone from filling the inbox.
    if not rate_limit.check("dugnadsand_contact", _client_ip(request), 5, 86400):
        form.add_error(None, "That's a few too many messages for one day. Try tomorrow.")
        return render(request, "site_app/index.html", {"form": form, "sent": False})

    if not INBOX:
        # Fail loudly in the log rather than quietly dropping someone's message.
        logger.error("DUGNADSAND_CONTACT_EMAIL is unset; contact form cannot deliver.")
        form.add_error(None, "The contact form isn't set up yet. Please try again later.")
        return render(request, "site_app/index.html", {"form": form, "sent": False})

    data = form.cleaned_data
    email.send(
        to=INBOX,
        subject=f"dugnadsand.org — {data['name']}",
        body=f"From: {data['name']} <{data['email']}>\n\n{data['message']}",
        site=SITE,
        reply_to=data["email"],
    )
    # Redirect after post so a refresh doesn't send it a second time.
    return redirect("/?sent=1#say-hello")


# --------------------------------------------------------------------------
# Policy attestation
#
# The manifest claims things about how this software behaves. A claim nobody
# can check is marketing, so the result is available two ways: on a schedule
# (Tempora POSTs to attestation_run) and on demand (anyone may GET attestation).
# --------------------------------------------------------------------------

ATTEST_TOKEN = os.environ.get("DUGNADSAND_ATTEST_TOKEN")


def attestation(request):
    """Public, read-only. The latest recorded run plus a live chain check.

    Deliberately shows the CURRENT result too, not only the last stored one, so
    a stale scheduler cannot make a green record look like a green system.
    """
    from policy import attest as attest_mod

    from .models import Attestation

    latest = Attestation.objects.order_by("-sequence").first()
    report = attest_mod.verify() if latest else None

    return render(request, "site_app/attestation.html", {
        "latest": latest,
        "live": attest_mod.attest(persist=False),
        "chain_ok": getattr(report, "ok", None),
        "chain_report": report,
        "disclaimer": attest_mod.DISCLAIMER,
    })


@csrf_exempt
@require_POST
def attestation_run(request):
    """Record an attestation. Called by Tempora; not for browsers.

    Token-guarded rather than open, because an unauthenticated writer could
    flood the chain and bury a real result under noise.
    """
    from policy import attest as attest_mod

    if not ATTEST_TOKEN:
        logger.error("DUGNADSAND_ATTEST_TOKEN is unset; refusing to record an attestation.")
        return JsonResponse({"error": "attestation is not configured"}, status=503)

    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not compare_digest(supplied, ATTEST_TOKEN):
        return JsonResponse({"error": "unauthorized"}, status=401)

    payload = attest_mod.attest()
    logger.info("Attestation #%s recorded: %s", payload["sequence"], payload["status"])
    return JsonResponse(payload, json_dumps_params={"default": str})


# --------------------------------------------------------------------------
# Claiming
#
# This function does not import, reference, or query Contribution. That absence
# is the load-bearing property of the whole system and is enforced two ways:
# statically by policy/checks.py (no function named *claim* may name
# Contribution) and at runtime by a test that drives a real claim and captures
# the SQL. If you are here to add "check they've contributed first" — read
# docs/design-rules.md §1 before you do.
# --------------------------------------------------------------------------


@login_required
@require_POST
def claim_offering(request, offering_id):
    from .models import Offering
    from .services import claim_offering as do_claim

    member = getattr(request.user, "member", None)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    offering = get_object_or_404(Offering, pk=offering_id)
    try:
        do_claim(offering=offering, member=member)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    return redirect("/")
