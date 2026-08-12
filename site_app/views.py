import logging
import os
from hmac import compare_digest

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import (Http404, HttpResponseBadRequest,
                         HttpResponseForbidden, JsonResponse)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from kjerne_platform import email, rate_limit

from .forms import ContactForm

logger = logging.getLogger(__name__)

WORK_TOML = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "work.toml")

SITE = "dugnadsand"
# Set per deployment; deliberately absent from the repo so no inbox is published.
INBOX = os.environ.get("DUGNADSAND_CONTACT_EMAIL")


def _client_ip(request):
    forwarded = request.META.get("HTTP_CF_CONNECTING_IP") or request.META.get(
        "HTTP_X_FORWARDED_FOR", ""
    )
    return forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")


@csrf_exempt
def _restamped(form):
    """Hand a rejected form back with a NEW stamp.

    Re-rendering the old one means the next attempt is judged on when the
    first page was drawn, so somebody who takes a minute to fix a typo gets
    told their form went stale — a dead end built out of the anti-spam check.
    """
    form.data = form.data.copy()
    form.data["t"] = ContactForm.stamp()
    return form


@csrf_exempt
def index(request):
    """The front page, and the contact form on it.

    CSRF-EXEMPT ON PURPOSE. The token protected nothing here — the attack it
    prevents is riding a logged-in session, and this form is anonymous — while
    costing at least one real visitor their message when their browser
    returned no cookies. What it incidentally did, keeping out bots that
    blind-POST, is now done by a signed timestamp in the form, which needs no
    cookie and works for somebody with everything blocked.

    Nothing else on this view acts on a session, which is what makes the
    exemption safe. Every authenticated form on the site still carries CSRF.
    """
    if request.method != "POST":
        return render(request, "site_app/index.html", {
            "form": ContactForm(initial={"t": ContactForm.stamp()}),
            "sent": request.GET.get("sent") == "1",
        })

    form = ContactForm(request.POST)
    if not form.is_valid():
        return render(request, "site_app/index.html",
                      {"form": _restamped(form), "sent": False})

    # Five a day per address keeps a bored someone from filling the inbox.
    if not rate_limit.check("dugnadsand_contact", _client_ip(request), 5, 86400):
        form.add_error(None, "That's a few too many messages for one day. Try tomorrow.")
        return render(request, "site_app/index.html",
                      {"form": _restamped(form), "sent": False})

    if not INBOX:
        # Fail loudly in the log rather than quietly dropping someone's message.
        logger.error("DUGNADSAND_CONTACT_EMAIL is unset; contact form cannot deliver.")
        form.add_error(None, "The contact form isn't set up yet. Please try again later.")
        return render(request, "site_app/index.html",
                      {"form": _restamped(form), "sent": False})

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


def csrf_failure(request, reason=""):
    """What somebody sees when a form's token does not check out.

    Only reachable for the authenticated forms now — the contact form on the
    front page is exempt, because a token on an anonymous form protects
    nothing and cost a real visitor their message. This used to carry a second
    branch that rebuilt the contact form with their words in it; that branch
    became unreachable the moment the exemption landed, and dead code that
    claims to help somebody is worse than none.

    Django's default is "CSRF verification failed. Request aborted.", which
    tells a person nothing they can act on.
    """
    # The old log line said only "Forbidden (CSRF cookie not set.)", which is
    # why the first occurrences could not be diagnosed at all.
    logger.warning(
        "CSRF failure on %s (%s) — cookies=%d origin=%r referer=%r ua=%r",
        request.path, reason, len(request.COOKIES),
        request.headers.get("Origin"), request.headers.get("Referer"),
        (request.headers.get("User-Agent") or "")[:120])

    # Two different truths. If the browser sent NO cookies it is not returning
    # ours either, and "try once more" sends somebody round a loop that cannot
    # end.
    return render(request, "site_app/csrf_failed.html",
                  {"reason": reason, "cookies_off": not request.COOKIES},
                  status=403)


# --------------------------------------------------------------------------
# Policy attestation
#
# The manifest claims things about how this software behaves. A claim nobody
# can check is marketing, so the result is available two ways: on a schedule
# (Tempora POSTs to attestation_run) and on demand (anyone may GET attestation).
# --------------------------------------------------------------------------

ATTEST_TOKEN = os.environ.get("DUGNADSAND_ATTEST_TOKEN")


def how_it_works(request):
    """The mechanics, publicly, for somebody deciding whether to use this.

    Static and unauthenticated. The front page is about the idea; this is about
    what the software does and refuses to do, and /attestation/ is the proof
    that the refusals hold. Three pages, three jobs — the front page was
    carrying all of them, which is how its ledger line drifted out of date.
    """
    return render(request, "site_app/how_it_works.html")


SECTIONS = (
    ("recorded", "About what is recorded"),
    ("decides", "About what the record may decide"),
    ("money", "About money and material"),
)


def policy(request):
    """The operating policy, read out of the manifest at render time.

    NOT a copy of docs/policy-statement.md. The commitments on this page are
    the ones policy/manifest.toml is enforcing right now — read from the file
    the checks run against, so the page cannot state a promise the code is not
    keeping, or omit one it is. A document alongside the manifest can only be
    tested for drift; a page generated from it cannot drift at all.

    Public and unauthenticated on purpose: a board deciding whether to adopt
    this needs to read it before anybody has an account.
    """
    from policy.attest import load_manifest

    manifest = load_manifest()
    by_group = {}
    for invariant in manifest["invariant"]:
        by_group.setdefault(invariant.get("group", "other"), []).append(invariant)

    sections = [(title, by_group.get(key, [])) for key, title in SECTIONS]
    # Anything the manifest grew without a group still appears. Silently
    # dropping a commitment from the page that exists to state them would be
    # the worst failure this page has.
    known = {key for key, _ in SECTIONS}
    leftover = [i for g, items in by_group.items() if g not in known for i in items]
    if leftover:
        sections.append(("Other commitments", leftover))

    return render(request, "site_app/policy.html", {
        "sections": sections,
        "version": manifest["manifest"]["version"],
        "count": len(manifest["invariant"]),
    })


def virtual_warehouse(request):
    """How material moves, for somebody who has not seen it work.

    Public: a business deciding whether to list a pallet needs to understand
    what they are and are not agreeing to before anybody gives them a login.

    The QR on the example is real and scannable and points back at this page.
    A live receipt link would be a working capability printed on a public
    document; a fake picture of one would teach somebody to trust a shape
    rather than a link.
    """
    from .auth_views import _qr_svg

    return render(request, "site_app/virtual_warehouse.html", {
        "example_qr": _qr_svg("https://dugnadsand.org/virtual-warehouse/"),
    })


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
    from .models import Member, Posting

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    # RLS scopes this to the member's organization; the filter is for openness.
    # claims are prefetched so the board can say who is already on something,
    # which is the coordination the board is for.
    open_postings = (
        Posting.objects.filter(open=True)
        .select_related("member", "project")
        # comments are prefetched for the reply count on every card; without
        # it the feed runs one query per posting.
        .prefetch_related("claims__member", "comments")
        .order_by("-created_at")
    )
    # Everybody else here, for the "thought of you" picker. Membership and
    # nothing else — a list narrowed by what somebody has given would be the
    # ledger deciding who gets asked.
    others = list(Member.objects.exclude(pk=member.pk)
                  .filter(user__isnull=False).exclude(user__email=""))

    # Claims are already prefetched, so this costs no query. Done here rather
    # than in the template because "am I on this" is a fact the view knows and
    # a template would have to loop to rediscover.
    open_postings = list(open_postings)
    for p in open_postings:
        p.i_am_on = any(c.member_id == member.id for c in p.claims.all())

    needs = [p for p in open_postings if p.kind == Posting.NEED]
    # Dated needs first, soonest at the top; undated ones keep their place at
    # the bottom in recency order. A need with no date is not less important,
    # it just has nothing to sort on, and inventing a position for it would be
    # inventing information.
    # Three bands, in this order: dated and still live, soonest first; then
    # past their date; then undated.
    #
    # Overdue used to sort FIRST, because ascending by needed_by puts the
    # oldest date at the top. That turned the most prominent position on the
    # board into a graveyard, and it got worse the longer the site ran — a
    # defect the timing feature could not show until something expired.
    #
    # They are not hidden. A date slipping does not mean the ride stopped being
    # wanted, and quietly dropping a real need would be worse than listing it
    # late. Their poster is asked about them instead.
    today = date.today()

    def band(p):
        if p.needed_by is None:
            return 2
        return 1 if p.needed_by < today else 0

    needs.sort(key=lambda p: (band(p),
                              p.needed_by or date.max,
                              -p.created_at.timestamp()))

    # ONE STREAM, not two headed lists. The ordering above is unchanged and
    # still never consults the person — what changes is that a reader sees a
    # single run of what is happening rather than two filing cabinets, with
    # the direction carried on each card instead of by a heading.
    #
    # Needs lead because a need has a date and an offer does not. That is a
    # fact about the posting, which is the only thing ordering is allowed to
    # be about.
    offers = [p for p in open_postings if p.kind == Posting.OFFER]
    feed = needs + offers

    # Resolved here rather than in the template: an organization admitted into
    # no chapter has region=None, and member.organization.region.name would
    # resolve to the invalid-variable marker rather than to nothing.
    region = member.organization.region
    return render(request, "site_app/board.html", {
        "section": "board",
        "member": member, "others": others,
        "feed": feed, "chapter": region.name if region else None,
        # Kept for anything still reading them, and for the counts in the lede.
        "needs": needs, "offers": offers,
    })


@login_required
def posting(request, posting_id):
    """One posting, and the conversation about it.

    THIS DID NOT EXIST, and comments were the casualty. A comment on a posting
    attached to a project was shown on the project page; a comment on a
    posting attached to NOTHING was written, stored, and displayed nowhere at
    all. Somebody typed it, pressed the button, and watched the page return to
    a board that had no idea it existed.
    """
    from .models import Member, Posting

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    post = get_object_or_404(
        Posting.objects.select_related("member", "project")
        .prefetch_related("claims__member", "comments__member"),
        pk=posting_id)
    post.i_am_on = any(c.member_id == member.id for c in post.claims.all())

    others = list(Member.objects.exclude(pk=member.pk)
                  .filter(user__isnull=False).exclude(user__email=""))

    return render(request, "site_app/posting.html", {
        "section": "board", "member": member, "p": post, "others": others,
        "comments": post.comments.all(),
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

    return render(request, "site_app/posting_form.html", {
        "section": "board","form": form})


@login_required
@require_POST
def step_off(request, posting_id):
    """Stop being the one on a posting. Only your own claim, ever.

    Deliberately not available to the poster. Letting whoever asked remove
    whoever answered would make the poster a manager of the people helping
    them, and there is no role like that here.
    """
    from .models import Posting
    from .notifications import announce_uncovered
    from .services import step_off as do_step_off

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    posting = get_object_or_404(Posting, pk=posting_id)
    try:
        remaining = do_step_off(posting=posting, member=member)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    # Only when the last person leaves. Still covered is not news.
    if remaining == 0:
        announce_uncovered(posting)
    return redirect(request.POST.get("back") or "/board/")


@login_required
@require_POST
def posting_close(request, posting_id):
    from .models import Posting

    member = _member(request)
    posting = get_object_or_404(Posting, pk=posting_id)
    if member is None or posting.member_id != member.id:
        return HttpResponseForbidden(
            "Only the person who posted it can take it down.")

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
    # Beside the hours, never added to them. The page said "work that was
    # done" and showed only one of the two records, which is the same
    # half-truth the front page told before material shipped.
    from .models import MaterialGiven

    material = (
        MaterialGiven.objects.select_related("member", "need", "need__project")
        .order_by("-recorded_at")[:200]
    )
    report = verify_contributions(member.organization)

    return render(request, "site_app/ledger.html", {
        "section": "ledger", "material": material,
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
def projects(request):
    """Everything ongoing here. No totals, no progress, no owner column."""
    from .models import Project

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    return render(request, "site_app/projects.html", {
        "member": member, "section": "projects",
        "open_projects": Project.objects.filter(open=True).select_related("started_by"),
        "finished": Project.objects.filter(open=False).select_related("started_by"),
    })


@login_required
def project_detail(request, project_id):
    """One project: what it is, what is open under it, what has gone into it.

    The last of those is a LOG in time order, deliberately not a sum. A project
    total is safe-looking — it describes work rather than a person — but with
    one contributor it IS that person's total, and with two it is close enough
    to subtract. See no-aggregate-display.
    """
    from .forms import MaterialNeedForm
    from .models import Contribution, Posting, Project

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    project = get_object_or_404(Project, pk=project_id)
    needs = list(project.needs.prefetch_related("given__member")
                             .select_related("added_by"))
    open_postings = list(
        Posting.objects.filter(project=project, open=True)
        .select_related("member").prefetch_related("claims"))
    for p in open_postings:
        p.i_am_on = any(c.member_id == member.id for c in p.claims.all())

    return render(request, "site_app/project_detail.html", {
        "member": member, "section": "projects", "project": project,
        "open_postings": open_postings,
        "went_in": Contribution.objects.filter(posting__project=project)
                                       .select_related("member", "posting")[:200],
        # Beside the hours, never added to them. The template says so out loud
        # rather than leaving the separation to be inferred.
        "needs": needs,
        "need_form": MaterialNeedForm(),
    })


@login_required
def project_new(request):
    from .forms import ProjectForm
    from .notifications import announce_project

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    form = ProjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        project = form.save(commit=False)
        project.started_by = member
        project.organization_id = member.organization_id
        project.save()
        announce_project(project)
        return redirect(f"/projects/{project.id}/")

    return render(request, "site_app/project_form.html",
                  {"form": form, "section": "projects"})


@login_required
@require_POST
def need_new(request, project_id):
    """Add a line to a project's bill of materials."""
    from .forms import MaterialNeedForm
    from .models import MaterialNeed, Project

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    project = get_object_or_404(Project, pk=project_id)
    form = MaterialNeedForm(request.POST)
    if form.is_valid():
        MaterialNeed.objects.create(
            organization_id=member.organization_id, project=project,
            description=form.cleaned_data["description"],
            quantity=form.cleaned_data["quantity"],
            unit=form.cleaned_data["unit"], added_by=member)
    return redirect(f"/projects/{project.id}/")


@login_required
def need_given(request, need_id):
    """Record material that arrived against a line."""
    from .forms import MaterialGivenForm
    from .models import MaterialNeed
    from .services_warehouse import record_material

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    need = get_object_or_404(MaterialNeed, pk=need_id)
    form = MaterialGivenForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        record_material(need=need, member=member,
                        quantity=form.cleaned_data["quantity"],
                        note=form.cleaned_data["note"])
        return redirect(f"/projects/{need.project_id}/")

    return render(request, "site_app/material_given_form.html",
                  {"form": form, "need": need, "section": "projects"})


@login_required
@require_POST
def project_close(request, project_id):
    """Mark it finished. Anyone in the organization may, including someone who
    never worked on it — there is no owner to ask, by design."""
    from .models import Project

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    project = get_object_or_404(Project, pk=project_id)
    project.open = False
    project.save(update_fields=["open"])
    return redirect("/projects/")


def act(request, token):
    """Spend a link somebody was emailed. No login, no session, one action.

    Deliberately not @login_required: the entire point is that the person
    holding this has no account. What protects it is the token itself — single
    use, time limited, and scoped to one verb with a payload fixed when it was
    issued, so nothing the holder sends can change what it does.

    Every refusal is byte-identical. "That link has expired" would tell a
    stranger that a link once existed, which is more than guessing should buy.
    """
    from kjerne_platform.work import port as work_port, tokens

    p = work_port.open(WORK_TOML)
    try:
        side, _ = tokens.redeem(p, token)
    except tokens.TokenRefused:
        return render(request, "site_app/act.html",
                      {"refused": True}, status=404)
    except Exception:
        logger.exception("token redemption failed")
        return render(request, "site_app/act.html",
                      {"refused": True}, status=404)

    return render(request, "site_app/act.html", {"side": side})


# --------------------------------------------------------------------------
# The virtual warehouse
#
# Every surface below shows a quantity WITH the age of its confirmation. A
# number on its own is a claim about the present tense that nobody checked, and
# somebody drives forty miles on it. Staleness must never render as
# availability — the same trap as reading an empty table as a measured zero.
# --------------------------------------------------------------------------

@login_required
def warehouse(request):
    """Everything on offer across every warehouse in this organization."""
    from .models import Warehouse
    from .services_warehouse import available_lines

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    return render(request, "site_app/warehouse.html", {
        "member": member, "section": "warehouse",
        "lines": available_lines(member.organization_id),
        "warehouses": Warehouse.objects.filter(active=True).select_related("holder"),
    })


@login_required
def warehouse_new(request):
    from .forms import WarehouseForm

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    form = WarehouseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        place = form.save(commit=False)
        place.holder = member
        place.organization_id = member.organization_id
        place.save()
        return redirect(f"/warehouse/{place.id}/")

    return render(request, "site_app/warehouse_form.html",
                  {"form": form, "section": "warehouse"})


@login_required
def warehouse_detail(request, warehouse_id):
    from .forms import StockLineForm
    from .models import StockLine, Warehouse
    from .services_warehouse import _now

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    place = get_object_or_404(Warehouse, pk=warehouse_id)
    form = StockLineForm(request.POST or None)

    # Only the holder adds stock. Anyone else writing a line would be asserting
    # what is in somebody else's barn.
    mine = place.holder_id == member.id
    if request.method == "POST" and mine and form.is_valid():
        StockLine.objects.create(
            organization_id=member.organization_id, warehouse=place,
            description=form.cleaned_data["description"],
            quantity=form.cleaned_data["quantity"],
            unit=form.cleaned_data["unit"],
            confirmed_at=_now(), confirmed_by=member)
        return redirect(f"/warehouse/{place.id}/")

    return render(request, "site_app/warehouse_detail.html", {
        "member": member, "section": "warehouse", "warehouse": place,
        "lines": place.lines.select_related("confirmed_by"),
        "form": form, "mine": mine,
    })


@login_required
@require_POST
def stock_confirm(request, line_id):
    """The holder saying it is still true. The only thing that moves the clock."""
    from .models import StockLine
    from .services_warehouse import confirm_line

    member = _member(request)
    line = get_object_or_404(StockLine, pk=line_id)
    if member is None or line.warehouse.holder_id != member.id:
        return HttpResponseForbidden(
            "Only whoever holds it can confirm what is there.")

    confirm_line(line=line, member=member,
                 quantity=request.POST.get("quantity") or None)
    return redirect(f"/warehouse/{line.warehouse_id}/")


@login_required
def stock_send(request, line_id):
    from .forms import SendMaterialForm
    from .models import StockLine
    from .services_warehouse import send_material, send_material_to_need

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    line = get_object_or_404(StockLine, pk=line_id)
    form = SendMaterialForm(request.POST or None, line=line,
                            initial={"need": request.GET.get("need") or None})
    if request.method == "POST" and form.is_valid():
        need = form.cleaned_data.get("need")
        try:
            if need is not None:
                # One story: the manifest records the movement and the project's
                # list records the arrival, joined by the manifest itself.
                manifest = send_material_to_need(
                    line=line, need=need, quantity=form.cleaned_data["quantity"],
                    member=member)
            else:
                manifest = send_material(
                    line=line, quantity=form.cleaned_data["quantity"],
                    destination=form.cleaned_data["destination"], member=member)
        except ValueError as exc:
            form.add_error("quantity", str(exc))
        else:
            return redirect(f"/manifest/{manifest.id}/")

    return render(request, "site_app/send_form.html",
                  {"form": form, "line": line, "section": "warehouse"})


@login_required
def manifest(request, manifest_id):
    """The paperwork that travels with the goods.

    Carries a QR to a single-use receipt link and NO VALUATION. Evidence that a
    thing moved is a different document from a statement of what it was worth,
    and only one of them is safe for a platform to produce.
    """
    from kjerne_platform.work import port as work_port
    from kjerne_platform.work import tokens

    from .auth_views import _qr_svg
    from .models import Manifest

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    doc = get_object_or_404(Manifest, pk=manifest_id)

    qr_svg = receipt_url = None
    if not doc.received:
        try:
            port = work_port.open(WORK_TOML)
            token = doc.receipt_token
            # Mint only when there is nothing usable. The code is PRINTED and
            # travels with the goods, so it has to be the same code every time
            # this page is rendered — and one live receipt link per page view
            # is a trail of capabilities nobody asked for.
            if not tokens.is_live(port, token):
                token = tokens.issue(
                    port, verb="confirm-receipt",
                    payload={"manifest": str(doc.id)}, tenant=doc.organization_id,
                    recipient=doc.destination[:200])
                doc.receipt_token = token
                doc.save(update_fields=["receipt_token"])
            receipt_url = f"https://dugnadsand.org/act/{token}/"
            qr_svg = _qr_svg(receipt_url)
        except Exception:
            # Paper that cannot be scanned is still paper. The manifest prints
            # either way and receipt can be recorded by hand.
            logger.exception("could not mint a receipt token")

    return render(request, "site_app/manifest.html", {
        "member": member, "section": "warehouse", "manifest": doc,
        "qr_svg": qr_svg, "receipt_url": receipt_url,
    })


# --------------------------------------------------------------------------
# Talking, keeping, pairing
# --------------------------------------------------------------------------

@login_required
@require_POST
def comment_new(request):
    """Say something about a posting or a project."""
    from .models import Posting, Project
    from .services_social import add_comment

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    posting = project = None
    if request.POST.get("posting"):
        posting = get_object_or_404(Posting, pk=request.POST["posting"])
        # Back to the posting itself. It used to be the project page, or the
        # board for a posting with no project — which meant a comment on a
        # project-less posting was written and then shown nowhere.
        back = f"/board/{posting.id}/"
    else:
        project = get_object_or_404(Project, pk=request.POST.get("project"))
        back = f"/projects/{project.id}/"

    try:
        add_comment(member=member, body=request.POST.get("body", ""),
                    posting=posting, project=project)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))
    return redirect(back)


@login_required
@require_POST
def pin_toggle(request):
    """Bookmark, privately. Nobody else sees this and nothing counts it."""
    from .models import Posting, Project
    from .services_social import toggle_pin

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    posting = project = None
    if request.POST.get("posting"):
        posting = get_object_or_404(Posting, pk=request.POST["posting"])
    else:
        project = get_object_or_404(Project, pk=request.POST.get("project"))

    toggle_pin(member=member, posting=posting, project=project)
    return redirect(request.POST.get("back") or "/board/")


@login_required
@require_POST
def point_at(request, posting_id):
    """Point somebody at a posting, and learn nothing about what came of it.

    The page says nothing back except that it was sent. There is no delivery
    state to show, no read receipt and no record of who was pointed at what —
    a sender who could see silence would read silence as refusal.
    """
    from .models import Member, Posting
    from .services_social import point_at as do_point

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    posting = get_object_or_404(Posting, pk=posting_id)
    target = get_object_or_404(Member, pk=request.POST.get("member"))
    do_point(posting=posting, to_member=target, from_member=member)

    messages.info(request, "Sent. You will not hear back through this — if they "
                           "take it on it shows on the board like anyone else.")
    return redirect(request.POST.get("back") or "/board/")


@login_required
@require_POST
def thanks(request, member_id):
    """Thank somebody. Sent and gone — no record, so nothing to count.

    Returns to where you were with nothing changed on the page, because there
    is nothing to show: no total went up, no badge appeared. That absence is
    the feature.
    """
    from .models import Member
    from .services_social import say_thanks

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    say_thanks(to_member=get_object_or_404(Member, pk=member_id),
               from_member=member)
    return redirect(request.POST.get("back") or "/board/")


@login_required
def pinned(request):
    from .services_social import pinned_for

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    return render(request, "site_app/pinned.html", {
        "member": member, "section": "pinned", "pins": pinned_for(member)})


@login_required
def pairings(request):
    """Facts sitting next to other facts, for a person to act on.

    Nothing here reads a member in order to decide what to show, so nothing
    here can rank one. Where a person ought to be asked, a person asks them.
    """
    from .services_social import fillable_needs, going_quiet, running_out

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    return render(request, "site_app/pairings.html", {
        "member": member, "section": "pairings",
        "running_out": running_out(),
        "fillable": fillable_needs(),
        "going_quiet": going_quiet(),
    })


@login_required
def manifests(request):
    """Paperwork, outstanding first.

    "What has not been signed for yet" is the question a sender actually has,
    and until this page existed a manifest was reachable only by URL in the
    moment it was made. Print it, close the tab, and the document was gone.
    """
    from .models import Manifest

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    docs = Manifest.objects.select_related(
        "stock_line", "stock_line__warehouse", "sent_by")
    return render(request, "site_app/manifests.html", {
        "member": member, "section": "warehouse",
        "outstanding": [d for d in docs if not d.received],
        "signed": [d for d in docs if d.received][:100],
    })


@csrf_exempt
@require_POST
def warehouse_sweep(request):
    """Housekeeping, called by Tempora. Not for browsers.

    Two jobs that only happen if something runs them, and neither had anything
    running it:

    Spent and expired capabilities are deleted. A token nobody can use is a row
    nobody should keep — it names a recipient and an item indefinitely.

    Holders of stock nobody has confirmed in three weeks are asked to look. The
    freshness clock is the honest part of this whole feature, and it only stays
    honest if somebody is prompted to move it. Told once per sweep, never
    chased.
    """
    from kjerne_platform.work import port as work_port
    from kjerne_platform.work import tokens

    from .models import Organization
    from .notifications import _send
    from .services_social import going_quiet
    from .tenancy import bypass_rls, tenant_context

    if not ATTEST_TOKEN:
        logger.error("DUGNADSAND_ATTEST_TOKEN is unset; refusing to sweep.")
        return JsonResponse({"error": "not configured"}, status=503)

    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not compare_digest(supplied, ATTEST_TOKEN):
        return JsonResponse({"error": "unauthorized"}, status=401)

    purged = tokens.purge()

    # Every organization, one at a time, each inside its own tenant. There is
    # no cross-tenant query here and there must not be: the sweep runs with no
    # session, so nothing would scope it but this loop.
    asked = 0
    with bypass_rls():
        organizations = list(Organization.objects.filter(active=True))

    for organization in organizations:
        with tenant_context(organization):
            for line in going_quiet():
                holder = line.warehouse.holder.user
                email = holder.email if holder else ""
                if email and _send(
                        email, "stale-stock",
                        "Something you are holding has not been confirmed in a while.",
                        "/warehouse/"):
                    asked += 1

    logger.info("warehouse sweep: %s tokens purged, %s holders asked", purged, asked)
    return JsonResponse({"tokens_purged": purged, "holders_asked": asked})


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
def you(request):
    """Your mark, and the colour of it. The only preference there is.

    There is deliberately nothing else on this page — no bio, no headline, no
    place to say what you are good at. A profile that describes what somebody
    offers becomes a directory of people ranked by what they offer, which is
    the catalog problem with faces attached.
    """
    from . import avatars

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    if request.method == "POST":
        chosen = request.POST.get("colour", "").strip()
        # Anything unrecognised clears the preference rather than storing it,
        # so the mark falls back to the colour derived from the id.
        member.avatar_colour = chosen if chosen in avatars.PALETTE else ""
        member.save(update_fields=["avatar_colour"])
        return redirect("/you/")

    return render(request, "site_app/you.html", {
        "member": member, "section": "you", "palette": avatars.PALETTE,
        "current": avatars.colour_of(member),
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
        "section": "members",
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

    return render(request, "site_app/member_form.html", {
        "section": "members","form": form, "created": created})


# --------------------------------------------------------------------------
# Work days. The one place in this system where something is withheld until a
# condition is met, and the condition is never a member — see WorkDay.
# --------------------------------------------------------------------------

@login_required
def work_days(request):
    """What is coming up, and what is still waiting on somebody's permission.

    Unannounced days are shown to members rather than hidden, because the
    thing a community needs to see is the day that is stuck: a blocker nobody
    can see is a phone call nobody makes.
    """
    from .models import WorkDay

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    days = (WorkDay.objects.filter(cancelled_at__isnull=True)
            .select_related("project", "called_by")
            .prefetch_related("clearances"))

    return render(request, "site_app/work_days.html", {
        "member": member, "section": "days",
        "announced": [d for d in days if d.published],
        "waiting": [d for d in days if not d.published],
        "cancelled": (WorkDay.objects.filter(cancelled_at__isnull=False)
                      .select_related("called_by")),
    })


@login_required
def work_day_new(request):
    from .forms import WorkDayForm
    from .services_events import call_work_day

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    form = WorkDayForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        day = call_work_day(
            organization=member.organization, member=member,
            project=form.cleaned_data["project"],
            name=form.cleaned_data["name"],
            description=form.cleaned_data["description"],
            starts_at=form.cleaned_data["starts_at"],
            ends_at=form.cleaned_data["ends_at"],
            place=form.cleaned_data["place"],
            muster=form.cleaned_data["muster"])
        return redirect(f"/days/{day.id}/")

    return render(request, "site_app/work_day_form.html",
                  {"member": member, "section": "days", "form": form})


@login_required
def work_day_detail(request, work_day_id):
    """The day, and everything standing between it and being announced."""
    from .forms import ClearanceForm
    from .models import WorkDay
    from .services_events import require_clearance

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    day = get_object_or_404(
        WorkDay.objects.select_related("project", "called_by"), pk=work_day_id)
    form = ClearanceForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        require_clearance(
            work_day=day, member=member, kind=form.cleaned_data["kind"],
            authority=form.cleaned_data["authority"],
            note=form.cleaned_data["note"])
        return redirect(f"/days/{day.id}/")

    return render(request, "site_app/work_day_detail.html", {
        "member": member, "section": "days", "day": day, "form": form,
        "clearances": day.clearances.select_related("raised_by"),
        "blockers": day.blockers,
    })


@login_required
def clearance_obtained(request, clearance_id):
    """Record that somebody outside said yes."""
    from .forms import ClearanceObtainedForm
    from .models import Clearance
    from .services_events import record_clearance

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    clearance = get_object_or_404(
        Clearance.objects.select_related("work_day"), pk=clearance_id)
    form = ClearanceObtainedForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        record_clearance(
            clearance=clearance,
            obtained_on=form.cleaned_data["obtained_on"],
            reference=form.cleaned_data["reference"],
            expires_on=form.cleaned_data["expires_on"],
            note=form.cleaned_data["note"] or clearance.note)
        return redirect(f"/days/{clearance.work_day_id}/")

    return render(request, "site_app/clearance_form.html", {
        "member": member, "section": "days", "form": form,
        "clearance": clearance, "day": clearance.work_day,
    })


@login_required
@require_POST
def work_day_publish(request, work_day_id):
    from .models import WorkDay
    from .services_events import NotCleared, publish

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    day = get_object_or_404(WorkDay, pk=work_day_id)
    try:
        publish(day)
    except NotCleared as refused:
        # Name every blocker, not the first. Otherwise somebody makes three
        # phone calls on three separate days.
        messages.error(request, "Not announced. Still waiting on: "
                                + "; ".join(f"{c.kind} from {c.authority}"
                                            for c in refused.blockers))
    else:
        messages.success(request, "Announced.")
    return redirect(f"/days/{day.id}/")


@login_required
@require_POST
def work_day_cancel(request, work_day_id):
    """Any member may call it off, as any member may close a project.

    Restricting it to whoever called the day would strand it the week that
    person is away, which is exactly when weather cancels things.
    """
    from .models import WorkDay
    from .services_events import cancel

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    day = get_object_or_404(WorkDay, pk=work_day_id)
    cancel(day, because=(request.POST.get("because") or "").strip())
    messages.success(request, "Called off.")
    return redirect(f"/days/{day.id}/")


@csrf_exempt
def apply(request):
    """Applying to join the network.

    CSRF-exempt with a signed stamp instead, exactly as the contact form is
    and for the same reason: this is an anonymous POST, so there is no session
    to ride, and the cookie requirement turned away real people on
    2026-08-11 while a blind-POSTing script was never troubled by it.

    Submitting an application admits nobody. /policy/ says there is no
    self-service signup and that stays true — this records a request, and the
    decision is still made by a person running a command.
    """
    from .forms import ApplicationForm
    from .services_applications import acknowledge, submit, tell_the_reviewer

    if request.method != "POST":
        form = ApplicationForm(initial={"t": ApplicationForm.stamp()})
        return render(request, "site_app/apply.html", {"form": form})

    form = ApplicationForm(request.POST)
    if not form.is_valid():
        form.data = form.data.copy()
        form.data["t"] = ApplicationForm.stamp()
        return render(request, "site_app/apply.html", {"form": form})

    application = submit(
        kind=form.cleaned_data["kind"],
        region=form.cleaned_data["region"],
        legal_name=form.cleaned_data["legal_name"],
        contact_name=form.cleaned_data["contact_name"],
        email=form.cleaned_data["email"],
        phone=form.cleaned_data["phone"],
        locality=form.cleaned_data["locality"],
        statement=form.cleaned_data["statement"],
        agreed=form.cleaned_data["agreed"],
        credentials=form.credentials())

    # The applicant's own words are NOT carried outside the boundary, the same
    # rule notifications follow: the fact of a record and nothing in it.
    logger.info("application received: %s (%s)",
                application.kind, application.id)

    # After the write, and both swallow their own failures: an application
    # recorded but unacknowledged is recoverable, one lost to a mail outage
    # is not.
    acknowledge(application)
    tell_the_reviewer(application, inbox=INBOX)

    return render(request, "site_app/apply_received.html",
                  {"kind": application.get_kind_display()})


# --------------------------------------------------------------------------
# Chapters. A roster and a map, never a lens: see Region's docstring for why
# a chapter cannot read into the organizations it admitted.
# --------------------------------------------------------------------------

def chapters(request):
    """Public: where there are chapters, and where there are not.

    The blank counties are the point. Somebody looking for their own area and
    finding it unshaded is the person the apply page is for.
    """
    from .models import Region

    regions = Region.objects.filter(active=True).prefetch_related(
        "organizations", "roles__user")

    covered = {}
    for region in regions:
        for area in region.areas:
            covered[area] = region

    shaded, total = _shaded_map({f"c-{a}": r.name for a, r in covered.items()})
    return render(request, "site_app/chapters.html", {
        "regions": regions,
        "map": shaded,
        # Counted from the map itself. A hardcoded total goes stale the moment
        # a state is added to it, and says the wrong thing confidently.
        "covered_count": len(covered),
        "county_count": total,
    })


def _shaded_map(covered):
    """The baked SVG with the covered counties marked, server-side.

    Done here rather than with a script on the page so the map is complete in
    the HTML: shading by JavaScript would show a visitor with none an entirely
    blank state, which reads as "no chapters anywhere" rather than as a page
    that has not finished.

    The SVG itself stays a plain map of South Carolina and knows nothing about
    chapters, so deploy/build_sc_map.py can regenerate it without being taught
    any of this.
    """
    import html
    import re

    from django.template.loader import render_to_string
    from django.utils.safestring import mark_safe

    svg = render_to_string("site_app/_counties.svg")

    def mark(match):
        element, ident = match.group(0), match.group(1)
        name = re.search(r'data-name="([^"]*)"', element)
        name = name.group(1) if name else ident
        if ident in covered:
            element = element.replace('class="county"', 'class="county held"')
            label = f"{name} — {covered[ident]}"
        else:
            label = f"{name} — no chapter yet"
        # A <title> inside the path is the accessible, no-JavaScript tooltip.
        return element[:-2] + f"><title>{html.escape(label)}</title></path>"

    marked, count = re.subn(r'<path id="(c-[a-z-]+)"[^>]*/>', mark, svg)
    return mark_safe(marked), count


@login_required
def chapter(request):
    """What an officer of a chapter can see.

    Everything on this page is ABOVE the tenant line: the names of the
    organizations admitted, who else holds a role, and the applications
    addressed to this chapter. Nothing from inside an organization appears
    here and nothing can — Region has no relation to any tenant-scoped model,
    so there is no query this view could make even by mistake. That is
    asserted in test_chapters.py rather than promised here.
    """
    from .models import Application

    roles = (request.user.region_roles
             .select_related("region")
             .prefetch_related("region__organizations", "region__roles__user"))
    if not roles:
        return HttpResponseForbidden("Not an officer of any chapter.")

    regions = []
    for role in roles:
        region = role.region
        waiting = (Application.objects
                   .filter(region=region, admitted__isnull=True)
                   .prefetch_related("credentials", "screenings"))
        regions.append({
            "region": region,
            "role": role,
            "officers": region.roles.all(),
            "organizations": region.organizations.all(),
            "waiting": [{"application": a, "blockers": a.blockers}
                        for a in waiting],
        })

    return render(request, "site_app/chapter.html",
                  {"regions": regions, "member": _member(request)})


# --------------------------------------------------------------------------
# The impact packet. What a project sends back to everybody who helped: an
# outcome, described and photographed, and never a figure for a tax return.
# --------------------------------------------------------------------------

@login_required
def project_packet(request, project_id):
    """Build the packet: measures, photos, and the words around them."""
    from .forms import ConsentForm, MeasureForm, PacketForm, PhotoForm
    from .models import Project
    from .services_packet import (UnitRefused, add_photo, build_packet,
                                  consent_blockers, consent_state,
                                  expect_consent, material_for, record_consent,
                                  record_measure, withdraw_consent)

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    project = get_object_or_404(Project, pk=project_id)
    packet = getattr(project, "packet", None)

    measure_form = MeasureForm()
    photo_form = PhotoForm()
    packet_form = PacketForm(initial={
        "title": packet.title if packet else project.name,
        "summary": packet.summary if packet else "",
        "acknowledgements": packet.acknowledgements if packet else ""})

    if request.method == "POST":
        what = request.POST.get("what")
        if what == "measure":
            measure_form = MeasureForm(request.POST)
            if measure_form.is_valid():
                try:
                    record_measure(project=project, member=member,
                                   **measure_form.cleaned_data)
                    return redirect(f"/projects/{project.id}/packet/")
                except UnitRefused as refused:
                    measure_form.add_error("unit", str(refused))
        elif what == "photo":
            photo_form = PhotoForm(request.POST, request.FILES)
            if photo_form.is_valid():
                try:
                    add_photo(
                        project=project, member=member,
                        upload=photo_form.cleaned_data["image"],
                        caption=photo_form.cleaned_data["caption"],
                        depicts_people=photo_form.cleaned_data["depicts_people"])
                    return redirect(f"/projects/{project.id}/packet/")
                except ValueError as refused:
                    photo_form.add_error("image", str(refused))
        elif what in ("consent", "withdraw"):
            from .models import Photo

            consent_form = ConsentForm(request.POST)
            photo = get_object_or_404(Photo, pk=request.POST.get("photo"))
            if consent_form.is_valid():
                fields = consent_form.cleaned_data
                if what == "withdraw":
                    withdraw_consent(
                        photo=photo, member=member, person=fields["person"],
                        withdrawn_on=timezone.localdate(), note=fields["note"])
                elif fields["given_on"]:
                    record_consent(
                        photo=photo, member=member, person=fields["person"],
                        given_on=fields["given_on"], how=fields["how"],
                        note=fields["note"])
                else:
                    expect_consent(
                        photo=photo, member=member, person=fields["person"],
                        note=fields["note"])
                return redirect(f"/projects/{project.id}/packet/")
        elif what == "packet":
            packet_form = PacketForm(request.POST)
            if packet_form.is_valid():
                build_packet(project=project, member=member,
                             **packet_form.cleaned_data)
                return redirect(f"/projects/{project.id}/packet/")

    photos = [{"photo": p, "consents": consent_state(p)}
              for p in project.photos.all()]

    return render(request, "site_app/packet_build.html", {
        "member": member, "section": "projects", "project": project,
        "packet": packet, "measures": project.measures.all(),
        "photos": photos, "material": material_for(project),
        "measure_form": measure_form, "photo_form": photo_form,
        "packet_form": packet_form, "consent_form": ConsentForm(),
        "consent_blockers": consent_blockers(project),
    })


@login_required
@require_POST
def packet_publish(request, project_id):
    from .models import Project
    from .services_packet import (ConsentOutstanding, publish_packet,
                                  withdraw_packet)

    member = _member(request)
    if member is None:
        return HttpResponseForbidden("Not a member of any organization.")

    project = get_object_or_404(Project, pk=project_id)
    packet = getattr(project, "packet", None)
    if packet is None:
        return HttpResponseBadRequest("There is no packet to publish yet.")

    if request.POST.get("withdraw"):
        withdraw_packet(packet)
        messages.success(
            request, "Withdrawn. The link that was sent out no longer works, "
                     "and publishing again mints a different one.")
    else:
        try:
            publish_packet(packet=packet, member=member)
        except ConsentOutstanding as refused:
            messages.error(
                request, "Not published. " + "; ".join(refused.blockers) + ".")
        else:
            messages.success(request, "Published.")
    return redirect(f"/projects/{project.id}/packet/")


def packet(request, token):
    """The published packet. No account, deliberately.

    Whoever this was sent to has no login and should not need one — the whole
    point is to hand somebody evidence of what their help became. What
    protects it is the token: unguessable, and dead the moment the packet is
    withdrawn.

    Reads through bypass_rls to find the packet, because an anonymous reader
    sets no tenant and RLS correctly hides everything. It then re-enters that
    packet's OWN tenant for the rest, so nothing wider is ever in scope.
    """
    from .models import Packet
    from .services_packet import material_for
    from .tenancy import bypass_rls, tenant_context

    if not token:
        raise Http404

    with bypass_rls():
        found = (Packet.objects.filter(token=token)
                 .exclude(token="")
                 .select_related("project", "organization").first())
        if found is None or not found.published:
            raise Http404

        organization = found.organization

    with tenant_context(organization):
        return render(request, "site_app/packet.html", {
            "packet": found, "project": found.project,
            "organization": organization,
            "measures": found.project.measures.all(),
            "photos": found.project.photos.all(),
            "material": material_for(found.project),
        })


def packet_photo(request, photo_id):
    """Serve a photo, and decide first whether the requester may have it.

    /media/ is routed nowhere on purpose. A file sitting under a web-served
    directory is public from the moment it is written, published packet or
    not, and "the URL is a UUID" is not an access rule.

    Two ways in: a member of the photo's own organization, or anybody at all
    once that project's packet is published. Withdrawing the packet closes the
    second door again.
    """
    from django.http import FileResponse

    from .models import Photo
    from .tenancy import bypass_rls

    with bypass_rls():
        photo = (Photo.objects.filter(pk=photo_id)
                 .select_related("project", "organization").first())
        if photo is None:
            raise Http404

        packet_of = getattr(photo.project, "packet", None)
        published = bool(packet_of and packet_of.published)
        organization_id = photo.organization_id
        image = photo.image

    member = _member(request)
    if not published and (member is None
                          or member.organization_id != organization_id):
        raise Http404

    try:
        return FileResponse(image.open("rb"))
    except FileNotFoundError:
        raise Http404
