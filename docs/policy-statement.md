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
the moment that page is loaded, so a stalled checker cannot make a stored pass
look like a current one.

## What this document is not

**It is not legal advice, a tax opinion, or a representation as to any
organization's obligations.** Those are matters for that organization's own
counsel and accountant. Nothing here should be relied on in their place.

**It is not a legal attestation.** The checks behind it are engineering checks:
they describe the behaviour of software. They certify compliance with no
statute, and no auditor has reviewed them.

It states what the software does and does not do. That behaviour is testable.

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

The commitments are not independent. A balance, a per-member total, a posted
rate, or a link between what a member received and what they gave would each
provide a route by which a contribution record could come to affect what a
member is given. `no-gating` states that property directly; the remaining
commitments remove the routes to it.

---

## 2. Where this system stops

**Dugnadsand does not reach the people who are helped.** It coordinates supply
between the groups that do — which material exists, where it is, and which
group can use it. Everything after that belongs to the group.

The division follows what each side is good at. A mutual aid group knows who on
its own street needs a roof repaired this month, and has no way of knowing that
a contractor forty miles away is about to skip the shingles. This system
addresses the second problem and leaves the first alone.

The consequence is that **no beneficiary is a party to this system.** Somebody
who needs help contacts a group directly through the page that lists them,
which carries no form and accepts no request. Who qualifies, what is offered
and what is decided are that group's questions, governed by that group's own
rules, and no record of any of it exists here.

Nothing is held either. Material listed in this system stays where its holder
keeps it; what is recorded is a description, a location and a count. The
platform is a directory, and the goods never enter its custody.

---

## 3. What is deliberately not promised

The following are outside the scope of the commitments above and are stated
explicitly.

**Individual contributions are visible.** The ledger is the chapter's log and
lists each entry under the contributor's name, readable by every member of
every organization in that chapter. This is intentional and
serves as recognition. No **total** is computed or displayed at any level: not
per member, not per project. Nothing prevents a reader tallying the entries
independently; the commitment constrains what the system computes and displays,
not what a person can count.

**Conduct between members is out of scope.** No software prevents members
observing who participates. These commitments concern what the system computes,
displays and decides.

**Donated material is not valued.** A manifest records that material moved,
from where, to whom and when. Its value is a matter for the donor, their adviser
and the relevant tax authority. A figure produced by this system would
constitute an appraisal of donated property generated by a platform concerning
a donor.

**No custody is taken.** Listed material remains where its holder keeps it. The
system records a location, a description and a quantity. It operates as a
directory rather than a warehouse and at no point holds title.

**Availability is a statement of last confirmation.** Every quantity is
displayed with the age of its confirmation. An unconfirmed listing may still be
present; only its holder can confirm or update it.

---

## 4. Chapters, organizations and what is shared

An organization is a party in the network: a household, a one-person business,
a not-for-profit, a congregation. Most are one or two people. A chapter is the
group of organizations covering one area, and it is admitted the same way —
deliberately, by a person, through an administrative step. There is no
self-service signup.

**The chapter is the boundary, not the organization.** Members of every
organization in a chapter see one another's offers, needs, projects, work days
and material, and may take up any of it. A network in which each organization
saw only its own board would be a set of separate boards.

Between chapters there is no visibility of any kind, and an organization
admitted into no chapter is visible to nobody but itself. That separation is
enforced by the database itself — Postgres row-level security, applied in the
same migration that creates each table — rather than by application code
remembering to filter. It **fails closed**: a mistake makes rows disappear
rather than leak.

What stays with the organization is authorship rather than sight. Every record
carries the organization of whoever wrote it, so a posting remains the posting
of the person who put it up, wherever it is read.

---

## 5. What leaves the boundary

Notifications, email and integrations traverse shared infrastructure that the
chapter separation does not cover. Data crossing that boundary carries
**the existence of a record and not its content**: the fact of a record, its
state, and a link. Message text and member names are excluded.

The link resolves inside the recipient's own chapter, under their own session.

**Single-use links.** Links issued for confirming a delivery or establishing an
account are single-use, expire, and authorise exactly one action fixed at the
time of issue. Spent and expired links are deleted on a schedule.

---

## 6. Changes to this statement

The manifest is versioned. A new commitment, or a change to an existing one, is
a change to `policy/manifest.toml` and appears in the published attestation from
the moment it lands.

Each attestation is appended to a hash chain in which every entry commits to its
predecessor, making an altered history detectable. The design is
**tamper-evident rather than tamper-proof**: an organization must retain the
ability to correct an error, honour a deletion request, or reverse a record
entered under pressure.

---

## 7. How to check any of this

| | |
|---|---|
| Live results | [dugnadsand.org/attestation](https://dugnadsand.org/attestation/) |
| The commitments, as code | [`policy/manifest.toml`](https://github.com/ewolters/dugnadsand/blob/master/policy/manifest.toml) |
| The checks behind them | [`policy/checks.py`](https://github.com/ewolters/dugnadsand/blob/master/policy/checks.py) |
| The reasoning | [`docs/design-rules.md`](https://github.com/ewolters/dugnadsand/blob/master/docs/design-rules.md) |
| The whole source | [github.com/ewolters/dugnadsand](https://github.com/ewolters/dugnadsand) |

A check whose subject does not yet exist reports **incomplete** rather than
passing, and a run cannot report an overall pass while any check is in that
state.

The software is published under the AGPL. Its network clause requires any party
running a modified copy to make that source available. A member can therefore
verify these commitments against the version their organization is running.

---

*Dugnadsand is sponsored by [SVEND](https://svend.ai). Questions about this
statement can go through the contact form at
[dugnadsand.org](https://dugnadsand.org/).*
