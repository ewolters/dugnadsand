"""Executable checks behind policy/manifest.toml.

Each check returns a Result with one of three statuses:

    upheld           the claim was tested and holds
    breached         the claim was tested and does not hold
    not_enforceable  the thing the claim is about does not exist yet

The third status is the point. A check that silently passes because there is
nothing to check is worse than no check at all — it reads as a green light. So
a check whose subject is absent says so, and attest.py refuses to call the
manifest upheld while any check is in that state.
"""

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from django.apps import apps

BASE_DIR = Path(__file__).resolve().parent.parent

UPHELD = "upheld"
BREACHED = "breached"
NOT_ENFORCEABLE = "not_enforceable"

# Models that carry the domain. Until these exist, most claims are about
# nothing and must not report green.
# The models the domain checks look at. _domain_models() only returns names
# from this tuple, so a check that loops over a name NOT in here raises a
# KeyError — and because /attestation/ runs the checks when it is drawn, that
# surfaces as a 500 on a public page rather than as a failing check. Adding a
# model to a check means adding it here in the same edit.
DOMAIN_MODELS = ("Posting", "Claim", "Contribution", "Interest", "Request")


@dataclass
class Result:
    id: str
    status: str
    detail: str
    evidence: list = field(default_factory=list)


def _domain_models():
    """Return the domain models that currently exist, by name."""
    found = {}
    for model in apps.get_models():
        if model.__name__ in DOMAIN_MODELS:
            found[model.__name__] = model
    return found


def _all_fields(model):
    return [f for f in model._meta.get_fields() if hasattr(f, "attname") or hasattr(f, "name")]


def _python_sources():
    """Every .py file in the project, excluding migrations and this package."""
    for path in BASE_DIR.rglob("*.py"):
        parts = path.parts
        # Tests are excluded: test_policy.py necessarily NAMES Contribution inside
        # a function called test_claiming_..., which would read as a breach of the
        # very claim it exists to verify.
        if ("migrations" in parts or "policy" in parts or ".venv" in parts
                or "tests" in parts):
            continue
        yield path


def _needs_domain(check_id, claim_about):
    missing = [m for m in DOMAIN_MODELS if m not in _domain_models()]
    if missing:
        return Result(
            check_id, NOT_ENFORCEABLE,
            f"{claim_about} cannot be tested: the domain models do not exist yet "
            f"(missing {', '.join(missing)}).",
        )
    return None


# ---------------------------------------------------------------- invariants

# Names that would mean a member holds a spendable quantity.
_BALANCE_NAMES = re.compile(
    r"balance|credit_limit|credits?|available_hours|owed|redeemable|wallet|funds", re.I
)


def no_balance():
    blocked = _needs_domain("no-balance", "The absence of balances")
    if blocked:
        return blocked

    hits = []
    for name, model in _domain_models().items():
        for f in _all_fields(model):
            fname = getattr(f, "name", "")
            if _BALANCE_NAMES.search(fname):
                hits.append(f"{name}.{fname}")

    if hits:
        return Result("no-balance", BREACHED,
                      "A field naming a spendable quantity exists.", hits)
    return Result("no-balance", UPHELD,
                  "No domain model carries a balance, credit limit, or spendable quantity.")


def no_gating():
    """Static half of the guard: the claim path must not name Contribution.

    The runtime half lives in site_app/tests/test_policy.py, which drives a real
    claim and captures the SQL. Two mechanisms, because a static check can be
    fooled by indirection and a runtime check can miss an untaken branch.
    """
    blocked = _needs_domain("no-gating", "The absence of gating")
    if blocked:
        return blocked

    hits = []
    for path in _python_sources():
        src = path.read_text()
        if "claim" not in src.lower():
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if "claim" not in node.name.lower():
                continue
            body = ast.dump(node)
            if "Contribution" in body:
                hits.append(f"{path.relative_to(BASE_DIR)}:{node.lineno} {node.name}()")

    if hits:
        return Result("no-gating", BREACHED,
                      "A claim path references the contribution record.", hits)
    return Result("no-gating", UPHELD,
                  "No claim path references the contribution record.")


# Modules that decide WHO HEARS ABOUT WHAT. Kept as an explicit list rather
# than a name heuristic: no_gating already showed what happens when a check
# infers its own scope from function names, and a routing module renamed to
# something clever would silently fall out of coverage. Adding a delivery path
# means adding it here, and the check fails loudly if a listed file is gone.
DELIVERY_MODULES = ("site_app/notifications.py",)


def no_routing_by_record():
    """The delivery layer must not know the contribution record exists.

    Deliberately blunt: any mention of Contribution anywhere in a delivery
    module is a breach, not just a mention inside a suggestively named
    function. There is no legitimate reason for the code that picks recipients
    to name the ledger, and a rule with no exceptions is a rule nobody has to
    argue about at review time.
    """
    present = [m for m in DELIVERY_MODULES if (BASE_DIR / m).exists()]
    if not present:
        return Result(
            "no-routing-by-record", NOT_ENFORCEABLE,
            "The absence of routing by record cannot be tested: no delivery "
            f"path exists yet (looked for {', '.join(DELIVERY_MODULES)}).",
        )

    hits = []
    for name in present:
        path = BASE_DIR / name
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            found = None
            if isinstance(node, ast.Name) and node.id == "Contribution":
                found = node.id
            elif isinstance(node, ast.Attribute) and node.attr == "Contribution":
                found = node.attr
            elif isinstance(node, ast.alias) and node.name == "Contribution":
                found = node.name
            if found:
                hits.append(f"{name}:{getattr(node, 'lineno', '?')} names {found}")

    if hits:
        return Result("no-routing-by-record", BREACHED,
                      "A delivery path references the contribution record.", hits)
    return Result(
        "no-routing-by-record", UPHELD,
        "No delivery path references the contribution record "
        f"({', '.join(present)}).")


# Measure and Packet are here although neither is material: both describe an
# outcome in a quantity and a unit, and both are read by somebody who gave
# something. A value field on either would be the appraisal this check exists
# to prevent, arriving through the impact packet instead of the warehouse.
#
# THIS TUPLE IS STILL HAND-MAINTAINED, which is the standing gap: a new
# quantity-bearing model nobody adds is unchecked while this reports UPHELD.
MATERIAL_MODELS = ("Warehouse", "StockLine", "Manifest",
                   "MaterialNeed", "MaterialGiven", "Measure", "Packet")

# Field names that would put a value on material, or make it commensurable with
# hours. Deliberately broad: this is the one place where a plausible-sounding
# addition does the most damage, so the check errs toward stopping a rename
# rather than toward letting a synonym through.
_VALUATION = re.compile(
    r"value|price|cost|worth|amount|apprais|assess|estimate|"
    r"fair_market|fmv|retail|msrp|rate|hours|hour_equiv|labou?r",
    re.I)


def no_material_valuation():
    """Material may be described and counted. It may never be priced.

    Also refuses any link from a material record to the hours ledger. A
    Contribution FK on a StockLine would be the equivalence written as a
    relation rather than a number, which is the same thing arriving by a
    different door.
    """
    from django.apps import apps

    present = {m.__name__: m for m in apps.get_models()
               if m.__name__ in MATERIAL_MODELS}
    if not present:
        return Result(
            "no-material-valuation", NOT_ENFORCEABLE,
            "The absence of material valuation cannot be tested: no material "
            f"record exists yet (looked for {', '.join(MATERIAL_MODELS)}).")

    hits = []
    for name, model in sorted(present.items()):
        for f in _all_fields(model):
            fname = getattr(f, "name", "")
            if _VALUATION.search(fname):
                hits.append(f"{name}.{fname} names a value or an hour equivalence")
            related = getattr(f, "related_model", None)
            if related is not None and related.__name__ == "Contribution":
                hits.append(f"{name}.{fname} links material to the hours ledger")

    if hits:
        return Result("no-material-valuation", BREACHED,
                      "A material record carries a value or an hour equivalence.",
                      hits)
    return Result(
        "no-material-valuation", UPHELD,
        "Material is described and counted, never priced and never converted "
        f"to hours ({', '.join(sorted(present))}).")


def no_exchange():
    blocked = _needs_domain("no-exchange", "The absence of exchange")
    if blocked:
        return blocked

    models = _domain_models()
    hits = []

    # A settlement link: Claim pointing at Contribution or the reverse.
    for a, b in (("Claim", "Contribution"), ("Contribution", "Claim")):
        for f in _all_fields(models[a]):
            related = getattr(f, "related_model", None)
            if related is not None and related.__name__ == b:
                hits.append(f"{a}.{getattr(f, 'name', '?')} -> {b}")

    # A two-party movement: any model with two FKs to the same member model.
    for model in apps.get_models():
        member_fks = [
            getattr(f, "name", "")
            for f in _all_fields(model)
            if getattr(f, "related_model", None) is not None
            and getattr(f.related_model, "__name__", "") == "Member"
        ]
        if len(member_fks) > 1:
            hits.append(f"{model.__name__} has {len(member_fks)} member links: {member_fks}")

    if hits:
        return Result("no-exchange", BREACHED,
                      "A record links what was received to what was given.", hits)
    return Result("no-exchange", UPHELD,
                  "Nothing links a claim to a contribution, and no record moves value between two members.")


_WEIGHTING_NAMES = re.compile(r"rate|multiplier|weight|skill|tier|level|value|price|amount|usd|dollar", re.I)


def flat_hours():
    blocked = _needs_domain("flat-hours", "Flat hours")
    if blocked:
        return blocked

    hits = []
    contribution = _domain_models()["Contribution"]
    for f in _all_fields(contribution):
        fname = getattr(f, "name", "")
        if _WEIGHTING_NAMES.search(fname):
            hits.append(f"Contribution.{fname}")

    if hits:
        return Result("flat-hours", BREACHED,
                      "A field that would weight or price an hour exists.", hits)
    return Result("flat-hours", UPHELD,
                  "Hours carry no weighting and no monetary denomination.")


# Payment rails. Presence of any of these means the software can move money.
_MONEY_PACKAGES = (
    "stripe", "mollie", "braintree", "paypal", "paypalrestsdk", "square",
    "squareup", "dwolla", "plaid", "adyen", "razorpay", "authorizenet",
    "coinbase", "web3", "stellar", "stellar_sdk", "py_stellar_base",
)


def no_money_rails():
    """Enforceable today: no payment package is declared or imported.

    This checks the code, not the content. A member writing "$100 available"
    in an offering description is intended behaviour — the manifest forbids the
    software gaining the ability to hold or move money, not people describing
    money they are giving away.
    """
    hits = []

    req = BASE_DIR / "requirements.txt"
    if req.exists():
        for line in req.read_text().splitlines():
            pkg = re.split(r"[<>=!\[ ]", line.strip(), 1)[0].lower().replace("-", "_")
            if pkg in _MONEY_PACKAGES:
                hits.append(f"requirements.txt declares {pkg}")

    for path in _python_sources():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            for n in names:
                if n.lower() in _MONEY_PACKAGES:
                    line = getattr(node, "lineno", "?")
                    hits.append(f"{path.relative_to(BASE_DIR)}:{line} imports {n}")

    if hits:
        return Result("no-money-rails", BREACHED,
                      "The system has acquired a way to move money.", hits)
    return Result("no-money-rails", UPHELD,
                  "No payment processor is declared or imported. The software cannot hold or move funds.")


# Things that would look like a substantiation receipt.
# [_\s-]? rather than [_-]?: the identifier forms were caught and the PROSE
# forms were not, so a template heading reading "Donation receipt" walked
# straight past a check whose whole job is documents. The impact packet is
# exactly the page that would grow one.
_TAX_ARTIFACT = re.compile(
    r"\b(1099|tax[_\s-]?receipt|donation[_\s-]?receipt|substantiation|deduct|"
    r"annual[_\s-]?statement|total[_\s-]?value|fair[_\s-]?market)\b", re.I
)


# A sentence that DENIES producing one of the above is not one of the above.
# Without this the check cannot be satisfied by any honest disclaimer: the
# impact packet has to be able to say, in words, that it cannot substantiate a
# deduction — and a check that forces a choice between honest copy and a green
# build will lose to the green build eventually.
#
# The same lesson as no-aggregate-display, which once matched a docstring
# explaining why .aggregate() is avoided. A text-scanning guard cannot tell a
# thing from prose about the thing, so it has to be told.
_DENIAL = re.compile(
    r"\b(no|not|never|cannot|can\'t|nothing|neither|nor|without|refuses?|"
    r"refused|prevents?|forbids?)\b", re.I)


def _sentence_around(text, position):
    """The clause a match sits in, bounded by punctuation or by markup.

    Angle brackets are boundaries so an HTML text node does not borrow a
    denial from the attribute of the tag before it.
    """
    starts = [text.rfind(c, 0, position) for c in (".", "\n", ">", ";")]
    start = max(starts) + 1
    ends = [text.find(c, position) for c in (".", "\n", "<", ";")]
    ends = [e for e in ends if e != -1]
    return text[start:min(ends) if ends else len(text)]


def no_tax_artifact():
    """Enforceable today: nothing RENDERS a per-member total or valuation.

    Denials are skipped — see _DENIAL. test_policy.py holds the other half by
    planting a real artifact and asserting this still catches it, because a
    skip rule with nothing testing it is a hole with a comment over it.
    """
    hits = []
    for path in list(_python_sources()) + list(BASE_DIR.rglob("*.html")):
        if "staticfiles" in path.parts or "docs" in path.parts:
            continue
        text = path.read_text(errors="ignore")
        for m in _TAX_ARTIFACT.finditer(text):
            if _DENIAL.search(_sentence_around(text, m.start())):
                continue
            line = text[: m.start()].count("\n") + 1
            hits.append(f"{path.relative_to(BASE_DIR)}:{line} '{m.group(0)}'")

    if hits:
        return Result("no-tax-artifact", BREACHED,
                      "Something in the system resembles a tax substantiation artifact.", hits)
    return Result("no-tax-artifact", UPHELD,
                  "The system produces no per-member valuation, total, or statement usable as substantiation.")


def no_catalog():
    blocked = _needs_domain("no-catalog", "The absence of a catalog")
    if blocked:
        return blocked

    hits = []
    for model in apps.get_models():
        if re.search(r"category|categories|tag|sku|service_type|rate_card", model.__name__, re.I):
            hits.append(f"model {model.__name__}")
    posting = _domain_models()["Posting"]
    for f in _all_fields(posting):
        fname = getattr(f, "name", "")
        if re.search(r"category|tag|sku|rate|suggested", fname, re.I):
            hits.append(f"Posting.{fname}")

    if hits:
        return Result("no-catalog", BREACHED, "A catalog or rate structure exists.", hits)
    return Result("no-catalog", UPHELD,
                  "Offerings are free text. No categories, rates, or suggested values.")


def no_obligation():
    blocked = _needs_domain("no-obligation", "The absence of obligation")
    if blocked:
        return blocked

    hits = []
    # Interest is here because it is the newest place a floor could appear:
    # it carries an offer of hours, and an offer that grew a minimum would be
    # a promise. The list is hand-maintained, which is the standing gap --
    # anything that records what somebody said they would do belongs in it.
    # Request is the sharpest case: it is the one record about a person who
    # is not a member, and a "was it resolved" field on it would be the whole
    # last-mile boundary crossed in a single migration.
    for name in ("Posting", "Claim", "Contribution", "Interest", "Request"):
        for f in _all_fields(_domain_models()[name]):
            fname = getattr(f, "name", "")
            if re.search(r"hours_min|minimum|required|commitment|reliability|"
                         r"completion|abandoned|no_show|score|rating", fname, re.I):
                hits.append(f"{name}.{fname}")

    if hits:
        return Result("no-obligation", BREACHED,
                      "A field exists that would make stopping cost something.", hits)
    return Result("no-obligation", UPHELD,
                  "Offers are ceilings. Nothing records a minimum, a completion, or a penalty for stopping.")


# Aggregating a member's hours turns a log into a score.
_AGGREGATION = re.compile(
    r"\b(Sum|Avg|Count)\s*\(\s*[\"']?(hours|contributions)|"
    r"\.aggregate\s*\(|"
    r"contributions\s*\|\s*length|"
    r"contributions\.count|"
    r"total_hours|hours_total|hours_given_total",
    re.I,
)


def _prose_lines(path, text):
    """Line numbers that are comment or docstring, for a Python source file.

    A text-scanning check cannot tell code from PROSE ABOUT CODE, and the
    difference matters: a docstring explaining why .aggregate() is avoided here
    contains the literal string it warns against. Without this, the check
    reports a breach on its own documentation, and the only way to a green
    build is to stop explaining the rule — which is how a guard quietly trades
    away the thing that makes it survivable.

    Comments and docstrings only. Ordinary string literals are still scanned,
    because a dict key of "total_hours" is a real hit rather than a discussion
    of one. Returns an empty set for anything that will not parse: unreadable
    source is scanned in full rather than skipped, which is the safe direction.
    """
    lines = set()
    for i, raw in enumerate(text.splitlines(), 1):
        if raw.lstrip().startswith("#"):
            lines.add(i)

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return lines

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            end = getattr(first, "end_lineno", first.lineno)
            lines.update(range(first.lineno, end + 1))
    return lines


def no_aggregate_display():
    """Enforceable today: nothing totals a member's hours, anywhere.

    Scans application code and templates. The log is allowed - and is the whole
    point - but a number that can be compared between members is a score, and a
    score reintroduces by social pressure exactly what no-gating removes from
    the code.
    """
    hits = []
    targets = list(_python_sources()) + [
        p for p in BASE_DIR.rglob("*.html")
        if "staticfiles" not in p.parts and "docs" not in p.parts
    ]
    for path in targets:
        text = path.read_text(errors="ignore")
        prose = _prose_lines(path, text) if path.suffix == ".py" else set()
        for m in _AGGREGATION.finditer(text):
            line = text[: m.start()].count("\n") + 1
            if line in prose:
                continue
            hits.append(f"{path.relative_to(BASE_DIR)}:{line} '{m.group(0).strip()}'")

    if hits:
        return Result("no-aggregate-display", BREACHED,
                      "Something totals contributed hours.", hits)
    return Result("no-aggregate-display", UPHELD,
                  "No per-member total of contributed hours is computed or displayed.")


# Every manifest entry's `check` must resolve here, and nothing may be here
# without a manifest entry. test_policy.py asserts both directions.
CHECKS = {
    "no_balance": no_balance,
    "no_gating": no_gating,
    "no_routing_by_record": no_routing_by_record,
    "no_material_valuation": no_material_valuation,
    "no_exchange": no_exchange,
    "flat_hours": flat_hours,
    "no_money_rails": no_money_rails,
    "no_tax_artifact": no_tax_artifact,
    "no_catalog": no_catalog,
    "no_obligation": no_obligation,
    "no_aggregate_display": no_aggregate_display,
}
