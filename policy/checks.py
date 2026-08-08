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
DOMAIN_MODELS = ("Offering", "Claim", "Contribution")


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
_TAX_ARTIFACT = re.compile(
    r"\b(1099|tax[_-]?receipt|donation[_-]?receipt|substantiation|deduct|"
    r"annual[_-]?statement|total[_-]?value|fair[_-]?market)\b", re.I
)


def no_tax_artifact():
    """Enforceable today: nothing renders a per-member total or valuation."""
    hits = []
    for path in list(_python_sources()) + list(BASE_DIR.rglob("*.html")):
        if "staticfiles" in path.parts or "docs" in path.parts:
            continue
        text = path.read_text(errors="ignore")
        for m in _TAX_ARTIFACT.finditer(text):
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
    offering = _domain_models()["Offering"]
    for f in _all_fields(offering):
        fname = getattr(f, "name", "")
        if re.search(r"category|tag|sku|rate|suggested", fname, re.I):
            hits.append(f"Offering.{fname}")

    if hits:
        return Result("no-catalog", BREACHED, "A catalog or rate structure exists.", hits)
    return Result("no-catalog", UPHELD,
                  "Offerings are free text. No categories, rates, or suggested values.")


def no_obligation():
    blocked = _needs_domain("no-obligation", "The absence of obligation")
    if blocked:
        return blocked

    hits = []
    for name in ("Offering", "Claim", "Contribution"):
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


# Every manifest entry's `check` must resolve here, and nothing may be here
# without a manifest entry. test_policy.py asserts both directions.
CHECKS = {
    "no_balance": no_balance,
    "no_gating": no_gating,
    "no_exchange": no_exchange,
    "flat_hours": flat_hours,
    "no_money_rails": no_money_rails,
    "no_tax_artifact": no_tax_artifact,
    "no_catalog": no_catalog,
    "no_obligation": no_obligation,
}
