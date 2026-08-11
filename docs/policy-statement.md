# Dugnadsand — Statement of Operating Policy

**Version 1 · effective 11 August 2026 · applies to dugnadsand.org and the
software behind it**

---

> **This is published at [dugnadsand.org/policy](https://dugnadsand.org/policy/).**
> That page reads its commitments straight out of `policy/manifest.toml` at
> render time, so it cannot drift; this file is the same statement in the
> repository, checked against the manifest by the test suite.

## What this document is

A plain statement of what this system does, what it deliberately does not do,
and how anybody can check either for themselves.

Every commitment below is bound to a named check that runs against the source
code continuously. The results are published, live, at
**[dugnadsand.org/attestation](https://dugnadsand.org/attestation/)** — run at
the moment that page is loaded, so a stalled checker cannot make a green record
look like a green system.

> **This is published at [dugnadsand.org/policy](https://dugnadsand.org/policy/).**
> That page reads its commitments straight out of `policy/manifest.toml` at
> render time, so it cannot drift; this file is the same statement in the
> repository, checked against the manifest by the test suite.

## What this document is not

**It is not legal advice, a tax opinion, or a representation about your
organization's obligations.** Those belong to your own counsel and accountant,
who know your circumstances. Nothing here should be relied on in place of them.

**It is not a legal attestation.** The checks behind it are engineering checks:
they describe the behaviour of software. They do not certify compliance with any
statute, and no auditor has reviewed them.

What it can tell you is exactly what the software does and does not do. That is
the part we can be held to, and it is the part that is testable.

---

## 1. The commitments

Each is enforced by the check named beside it. The wording is drawn from
`policy/manifest.toml`, which is the operative version; if this document and the
manifest ever disagree, the manifest is correct and this document is stale.

### About what is recorded

| | |
|---|---|
| `no-balance` | No member holds a balance, credit limit, or any spendable quantity. |
| `flat-hours` | An hour counts as one hour, from anyone, and is never denominated in money. |
| `no-aggregate-display` | Nothing computes or displays a per-member total of contributed hours. |
| `no-catalog` | Postings are free text. No categories, rates, or suggested values. |

### About what the record may decide

| | |
|---|---|
| `no-gating` | No code path consults what a member has given when deciding what they may receive. |
| `no-routing-by-record` | No code path consults what a member has given when deciding who to tell about a need. |
| `no-obligation` | An offer of time is a ceiling with no floor, and stopping is recorded nowhere. |

### About money and material

| | |
|---|---|
| `no-money-rails` | The system integrates no payment processor and moves no funds. |
| `no-exchange` | Nothing links what a member received to what a member gave. |
| `no-material-valuation` | No record of material carries a value, a price, or an equivalence in hours. |
| `no-tax-artifact` | The system emits no per-member valuation, total, or statement that could function as tax substantiation. |

**The single load-bearing commitment is `no-gating`.** Everything else exists to
protect it. A system where giving earns standing is an exchange whatever it is
called, and an organization offering help without eligibility requirements
cannot run on one.

---

## 2. What is deliberately not promised

An honest statement is as useful for what it refuses to claim.

**Individual contributions are visible.** The ledger is the organization's own
log and lists each entry by name. That is intended — it is recognition, and it
is how a community sees its own work. What does not exist is a **total**: not
per member, not per project, not your own. A number that can be compared
between people is a score, and a score reintroduces through social pressure
exactly what the code removes.

**We cannot govern what people say to each other.** No software prevents someone
noticing who turns up. The commitments are about what the system computes,
displays and decides.

**We do not value donated material, and will not.** A manifest records that
goods moved, from where, to whom and when. What they were worth is a question
for the donor, their advisor and the tax authority. Any figure this system
produced would be an appraisal of donated property written by a platform about
a donor, which is the one document it must never generate.

**We take no custody of anything.** Material listed here stays where its holder
keeps it. The system records a location, a description and a count; it is a
directory, not a warehouse, and it never holds title.

**Availability is a claim about when somebody last looked.** Every quantity is
shown with the age of its confirmation. A listing that has gone quiet may well
still be there — only its holder can say, and only its holder can update it.

---

## 3. Organizations and separation

Each organization is admitted deliberately, by a person, through an
administrative step. There is no self-service signup.

Its members, postings, ledger, projects and material are invisible to every
other organization. That separation is enforced by the database itself —
Postgres row-level security, applied in the same migration that creates each
table — rather than by application code remembering to filter. It **fails
closed**: a mistake makes rows disappear rather than leak.

---

## 4. What leaves the boundary

Notifications, emails and integrations travel through shared infrastructure that
the per-organization separation does not reach. Anything crossing that boundary
therefore carries **the signal and not the content**: that something exists, its
state, and a link. Never the words somebody wrote, never a member's name.

The link resolves under the reader's own session, inside their own organization,
which is where that content belongs.

**Single-use links.** Somebody signing for a delivery, or setting up an account,
receives a link that works once, expires, and authorises exactly one action
decided when it was issued. Spent and expired links are deleted on a schedule.

---

## 5. Changes to this statement

The manifest is versioned. A new commitment, or a change to an existing one, is
a change to `policy/manifest.toml` and appears in the published attestation from
the moment it lands.

Every attestation is appended to a hash chain: each entry commits to the one
before it, so an altered history is detectable rather than merely unlikely. It
is deliberately **tamper-evident and not tamper-proof** — a community must be
able to correct an honest mistake, honour a deletion request, or unwind a record
made under pressure. A ledger nobody can amend is a ledger that has to be right
the first time.

---

## 6. How to check any of this

| | |
|---|---|
| Live results | [dugnadsand.org/attestation](https://dugnadsand.org/attestation/) |
| The commitments, as code | [`policy/manifest.toml`](https://github.com/ewolters/dugnadsand/blob/master/policy/manifest.toml) |
| The checks behind them | [`policy/checks.py`](https://github.com/ewolters/dugnadsand/blob/master/policy/checks.py) |
| The reasoning | [`docs/design-rules.md`](https://github.com/ewolters/dugnadsand/blob/master/docs/design-rules.md) |
| The whole source | [github.com/ewolters/dugnadsand](https://github.com/ewolters/dugnadsand) |

A check whose subject does not exist yet reports **incomplete** rather than
passing, and a run can never read green while any check is in that state. An
honest amber is the right answer until the thing is built.

The software is published under the AGPL, whose network clause means anybody
running a modified copy must be able to show its source. That is doing specific
work here: it is what lets a member of a community ask that community to prove
these commitments still hold in the version they are actually running.

---

*Dugnadsand is sponsored by [SVEND](https://svend.ai). Questions about this
statement can go through the contact form at
[dugnadsand.org](https://dugnadsand.org/).*
