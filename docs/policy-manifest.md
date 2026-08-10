# The policy manifest

## Read this first

**This is an engineering manifest. It is not a legal attestation, and nothing in it
should ever be quoted as one.**

What it says is narrow and literal: *these automated checks ran against this codebase at
this time, and this is what they returned.* That is all.

What it does **not** say, and cannot say:

- that the model is lawful
- that any tax treatment applies, or that gifts here are or are not reportable
- that any federal or state authority agrees with any characterisation in these docs
- that counsel has reviewed anything — **none of this has been reviewed by counsel**
- that an organisation running this software is compliant with anything

The manifest is a machine checking whether the software still behaves the way we said it
behaves. A green result means the code has not drifted. It does not mean the idea is
sound, and it confers no protection on anyone.

If this document ends up in front of a board, a regulator, an auditor or an attorney,
that paragraph is the part that matters. The word *attestation* appears throughout this
codebase in its ordinary engineering sense — a record that a check ran — and never in the
sense of a professional attestation engagement.

---

## Why it exists

The rest of the documentation makes claims. [design-rules.md](design-rules.md) says
nothing gates on what you have given. [architecture.md](architecture.md) says there is no
balance to be insufficient. [board-case.md](board-case.md) repeats both to a board that
will decide something on the strength of them.

Claims like that decay. Someone adds a helpful sort order, a reliability badge, a
suggested-hours hint — each reasonable in isolation, each quietly undoing a property the
model rests on. Prose in a repository does not stop that. A failing build does.

So every load-bearing claim is written twice: once in
[`policy/manifest.toml`](../policy/manifest.toml) for people, and once in
[`policy/checks.py`](../policy/checks.py) as something that runs.

---

## The three prohibitions, specifically

Three of the eight invariants exist because of questions raised directly by the people
building this. They are worth stating plainly.

### No hours may be exchanged for hours

`no-exchange` fails if anything links what a member received to what a member gave — a
foreign key between a claim and a contribution, or any record holding two member
references in a payer/payee shape.

Two gifts that happen to run in opposite directions are still two gifts. A record that
*ties them together* is a barter transaction, and the distinction is exactly the one that
matters. The check enforces the absence of the tie, not the absence of reciprocity —
neighbours helping each other back is the entire point and is not what this forbids.

### No money may move through the system

`no-money-rails` fails if any payment package is declared in `requirements.txt` or
imported anywhere: Stripe, Mollie, PayPal, Square, Dwolla, Plaid, Adyen, and the
blockchain SDKs among them.

**This is a check on the code, not on what members write.** A member posting *"$100
available, took me an hour to earn"* is intended behaviour. The system reading that as
free text and routing the offer to somebody who needs it is precisely the design. What is
forbidden is the software itself gaining the ability to hold, transfer or settle funds —
because the moment it can, the questions in [board-case.md](board-case.md) §3 change
character entirely.

The distinction in one line: **people may describe money; the system may not touch it.**

### No tax artifact may be produced

`no-tax-artifact` fails on any per-member valuation, running total, annual statement, or
anything matching the vocabulary of substantiation — `1099`, `deduct`, `fair market`,
`donation receipt`.

Donated services are not deductible (Treas. Reg. §1.170A-1(g)). A statement totalling
someone's contributions — especially with a currency figure on it — would invite a
deduction that does not exist, and would push the record toward looking exactly like the
barter-exchange statement this model is built to avoid. The safest artifact is none.

---

## Two claims added since, and why each needed its own

The manifest started at nine. Both additions came from the same discovery: a
new capability opens a **surface** the existing checks cannot see, and a check
that cannot see a surface reports green across it.

**`no-routing-by-record`** arrived with notifications. `no-gating` scans
functions whose *name* contains "claim" for references to the contribution
record — exact while claiming was the only place eligibility could hide. The
moment the system started deciding who to tell about a need, that logic moved
into a function called `_audience`, which `no-gating` does not look at.

The feature somebody will propose is *"send needs to whoever actually turns
up"*. It sounds like good engineering and it is gating: a member who has given
nothing hears about fewer needs, so the record has begun deciding what reaches
whom. Withholding the chance to help is a softer denial than refusing a claim,
and it is still a denial.

**`no-material-valuation`** arrived with the warehouse. `flat-hours` is about
hours and `no-tax-artifact` scans for per-member statements; neither could see
a price on a pallet. It forbids two conversions — a value on material, and an
equivalence between material and hours — and it fails on a database relation to
the contribution ledger as readily as on a field called `value`, because that
conversion arrives as a foreign key at least as often as a number.

**The rule this gives us:** when a capability opens a new surface, ask which
existing check covers it. If the honest answer is *none, because they scan
somewhere else*, that is a new invariant rather than a widened old one. Widening
a check to cover a second surface tends to make it vaguer at the first.

## How it runs

**Daily.** Tempora POSTs to `/attestation/run/` at 09:00 UTC via
`workers.http_dispatch.dispatch`, so the scheduler needs no knowledge of this app. The
seed is in [`deploy/tempora-attestation.sql`](../deploy/tempora-attestation.sql).

**On demand.** [dugnadsand.org/attestation](https://dugnadsand.org/attestation/) is
public and unauthenticated. It shows the last recorded run *and* re-runs the checks live
as you load it, so a stalled scheduler cannot leave a stale green record standing in for a
system that has since changed.

**In CI.** `site_app/tests/test_policy.py` runs every check and fails the build on any
breach, so a breach cannot reach production and wait for the scheduler to notice.

**Chained.** Each run is appended to a hash chain (`kjerne_platform.chain`), every entry
committing to the one before it. Rewriting a past result breaks every hash after it —
there is a test that does exactly this and asserts the chain refuses to verify.

The records live in Postgres rather than a file in this repository, deliberately: a
scheduled job that writes a git-tracked artifact loses its output on every tree clean,
and the schedule keeps reporting healthy while the artifact quietly freezes.

---

## Three results, and why the middle one matters

| | Meaning |
|---|---|
| `UPHELD` | every claim was tested and holds |
| `INCOMPLETE` | nothing was breached, but something could not be tested |
| `BREACHED` | at least one claim was tested and does not hold |

**`INCOMPLETE` is not a soft pass, and it can never be reported as `UPHELD`.**

A check whose subject does not exist yet returns *not enforceable* rather than passing.
The alternative — passing because there was nothing to find — is the failure mode a
manifest invites, and it is the most dangerous possible reading, because a green light is
least deserved exactly when the thing it protects has not been built.

At the time of writing the run reports:

```
STATUS: INCOMPLETE   upheld: 2   not_enforceable: 6   breached: 0
```

Two claims hold today and are genuinely enforced: no payment rails, no tax artifact. Six
cannot yet be tested, because the ledger they describe has not been built. The manifest
says so, and will keep saying so until it is.

That amber is the honest answer, and the list of unenforceable checks doubles as the
punch list.

---

## Adding or changing a claim

1. Add the entry to `policy/manifest.toml` with an `id`, the `claim`, a real `why`, and
   the name of its `check`.
2. Implement that check in `policy/checks.py` and register it in `CHECKS`.
3. Run the suite. It fails if a claim has no implementation, if an implementation has no
   claim, if a rationale is thin, or if the manifest ever stops declaring
   `legal_effect = "none"`.

Editing the manifest changes its hash, which is recorded inside every attestation — so an
older record is visibly about older wording rather than silently reinterpreted under new.

**Loosening a claim should be uncomfortable.** It means the software is about to do
something the documents told a board it would not. That is a decision for the board, not
a commit.
