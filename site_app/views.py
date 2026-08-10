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
def claim_posting(request, posting_id):
    from .models import Posting
    from .notifications import announce_claim
    from .services import claim_posting as do_claim

    member = getattr(request.user, "member", None)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    posting = get_object_or_404(Posting, pk=posting_id)
    try:
        claim = do_claim(posting=posting, member=member)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    announce_claim(claim)
    return redirect("/board/")


# --------------------------------------------------------------------------
# The member application
#
# Deliberately absent from every view below: any per-member total, any ordering
# by contribution, any eligibility check. Members see a LOG of what has been
# given, never a score — the record is recognition, and a number people can
# compare is a score whatever we call it. See docs/design-rules.md §1.
# --------------------------------------------------------------------------


def member_login(request):
    from django.contrib.auth import authenticate, login
    from kjerne_platform import login_protection

    from .forms import MemberLoginForm

    form = MemberLoginForm(request.POST or None)
    error = None

    if request.method == "POST" and form.is_valid():
        username = form.cleaned_data["username"]
        if not login_protection.check_login(request, username):
            error = "Too many attempts. Try again in a few minutes."
        else:
            user = authenticate(
                request, username=username, password=form.cleaned_data["password"])
            if user is None:
                error = "That username and password do not match."
            else:
                login(request, user)
                return redirect("/board/")

    return render(request, "site_app/login.html", {"form": form, "error": error})


def member_logout(request):
    from django.contrib.auth import logout

    logout(request)
    return redirect("/")


def _member(request):
    return getattr(request.user, "member", None)


@login_required
def board(request):
    """Everything open in this member's organization, both directions.

    Needs are ordered by when they are needed, then by recency. Offers stay in
    recency order — an offer has no deadline to sort by.

    The invariant is not "order by recency", it is that ORDER NEVER CONSULTS
    THE PERSON. Sorting a need by its own date is a fact about the need;
    sorting it by its asker's contribution would make the record function as
    standing, which is the exact failure this system exists to avoid. See
    no-gating in policy/manifest.toml.
    """
    from datetime import date
    from .models import Posting

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    # RLS scopes this to the member's organization; the filter is for openness.
    # claims are prefetched so the board can say who is already on something,
    # which is the coordination the board is for.
    open_postings = (
        Posting.objects.filter(open=True)
        .select_related("member")
        .prefetch_related("claims__member")
        .order_by("-created_at")
    )
    needs = [p for p in open_postings if p.kind == Posting.NEED]
    # Dated needs first, soonest at the top; undated ones keep their place at
    # the bottom in recency order. A need with no date is not less important,
    # it just has nothing to sort on, and inventing a position for it would be
    # inventing information.
    needs.sort(key=lambda p: (p.needed_by is None,
                              p.needed_by or date.max,
                              -p.created_at.timestamp()))
    return render(request, "site_app/board.html", {
        "member": member,
        "needs": needs,
        "offers": [p for p in open_postings if p.kind == Posting.OFFER],
    })


@login_required
def posting_new(request):
    from .forms import PostingForm
    from .notifications import announce_posting

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    form = PostingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        posting = form.save(commit=False)
        posting.member = member
        posting.organization_id = member.organization_id
        posting.save()
        # Everyone else in the organization, chosen by membership and nothing
        # else. Fails open — see site_app/notifications.py.
        announce_posting(posting)
        return redirect("/board/")

    return render(request, "site_app/posting_form.html", {"form": form})


@login_required
@require_POST
def posting_close(request, posting_id):
    from .models import Posting

    member = _member(request)
    posting = get_object_or_404(Posting, pk=posting_id)
    if member is None or posting.member_id != member.id:
        return HttpResponseForbidden("Only the person who offered it can close it.")

    posting.open = False
    posting.save(update_fields=["open"])
    return redirect("/board/")


@login_required
def contribution_new(request, posting_id):
    """Write down hours that were given.

    Recording hours is a separate act from claiming, and the two never meet in
    a row — see no-exchange.
    """
    from .forms import ContributionForm
    from .models import Posting
    from .services import record_contribution

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    posting = get_object_or_404(Posting, pk=posting_id)
    form = ContributionForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            record_contribution(
                member=member,
                posting=posting,
                hours=form.cleaned_data["hours"],
                note=form.cleaned_data["note"],
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            return redirect("/ledger/")

    return render(request, "site_app/contribution_form.html",
                  {"form": form, "posting": posting})


@login_required
def ledger(request):
    """The organization's contribution log.

    A list, in time order, with no totals and no per-member aggregation. It
    reads like a commit log because that is exactly what it is: visible work,
    conferring standing on nobody.
    """
    from .models import Contribution
    from .services import verify_contributions

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    entries = (
        Contribution.objects.select_related("member", "posting")
        .order_by("-recorded_at")[:200]
    )
    report = verify_contributions(member.organization)

    return render(request, "site_app/ledger.html", {
        "entries": entries,
        "chain_ok": getattr(report, "ok", None),
    })


# --------------------------------------------------------------------------
# Passwords and organizers
#
# A member arrives with a password somebody else typed and read aloud. Until
# they replace it, the person who added them can sign in as them — so the
# change is forced rather than suggested.
# --------------------------------------------------------------------------


@login_required
def notices(request):
    """What has happened here lately, and nothing about who did it.

    Opening this page marks everything read. There is deliberately no record
    of that going anywhere useful: a sender who could see that a notice was
    delivered and not acted on would be watching for a response, and being
    watched for a response is an obligation. Nobody here owes anybody an
    answer — see docs/design-rules.md.
    """
    from .notifications import mark_read_here, recent_here

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    email = request.user.email
    try:
        items = recent_here(email, limit=50) if email else []
        # Explicit ids. Clearing by address alone would dismiss notices raised
        # by other federation sites — see site_app/notifications.py.
        mark_read_here(email, [n["id"] for n in items if n["read_at"] is None])
    except Exception:
        logger.warning("notices unavailable", exc_info=True)
        items = None  # distinct from "nothing here" — the template says so

    return render(request, "site_app/notices.html", {
        "member": member, "items": items, "section": "notices",
    })


@login_required
def change_password(request):
    from django.contrib.auth import update_session_auth_hash
    from django.contrib.auth.forms import PasswordChangeForm

    member = _member(request)
    form = PasswordChangeForm(request.user, request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        # Changing a password rotates the session hash; without this the member
        # is signed out by their own success.
        update_session_auth_hash(request, form.user)
        if member is not None and member.must_change_password:
            member.must_change_password = False
            member.save(update_fields=["must_change_password"])
        return redirect("/board/")

    return render(request, "site_app/password_change.html", {
        "form": form,
        "forced": bool(member and member.must_change_password),
    })


@login_required
def members(request):
    """Who is in this organization.

    Shows names and roles. Deliberately NOT what anyone has given: a members
    page is exactly where an hours column would feel natural, and that column
    would turn the record into standing. See policy/manifest.toml,
    no-aggregate-display.
    """
    from .models import Member

    member = _member(request)
    if member is None or not member.is_organizer:
        return HttpResponseForbidden("Only organizers can see the member list.")

    return render(request, "site_app/members.html", {
        "member": member,
        "members": Member.objects.order_by("display_name"),
    })


@login_required
def member_new(request):
    from .forms import AddMemberForm
    from .services_members import MemberExists, create_member

    member = _member(request)
    if member is None or not member.is_organizer:
        return HttpResponseForbidden("Only organizers can add members.")

    form = AddMemberForm(request.POST or None)
    created = None

    if request.method == "POST" and form.is_valid():
        try:
            new_member, password = create_member(
                organization=member.organization,
                username=form.cleaned_data["username"],
                display_name=form.cleaned_data["display_name"],
                email=form.cleaned_data["email"],
                is_organizer=form.cleaned_data["is_organizer"],
            )
        except (MemberExists, ValueError) as exc:
            form.add_error(None, str(exc))
        else:
            # Rendered once and never stored. Reloading the page loses it,
            # which is the correct behaviour for a credential.
            created = {"member": new_member,
                       "username": form.cleaned_data["username"].strip(),
                       "password": password}
            form = AddMemberForm()

    return render(request, "site_app/member_form.html", {"form": form, "created": created})
