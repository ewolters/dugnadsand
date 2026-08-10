# How it works

For somebody deciding whether their organization should use this.

The front page explains the idea. This explains the mechanics: what the system
records, what it deliberately does not, and how you can check that for
yourself rather than taking our word for it.

---

## Four things people share here

**Hours.** Somebody does something and it gets written down. Thirteen hours on
a community garden. That is the entire entry.

**Things on offer, and things needed.** A board that runs both directions. Post
what you have, post what you need, and anyone can take up either. Nobody has to
have given first.

**Ongoing work.** A project gathers related postings — repairing homes on the
east side, keeping the food pantry stocked. Nobody is put in charge of one, and
anyone can mark it finished, including somebody who never worked on it. There
is no owner to ask.

**Material.** The part most systems miss. See below.

---

## What the record is not

It is not a currency. Hours cannot be spent, are not owed by anyone to anyone,
and buy nothing.

**Nothing in the system gates on what you have given.** You can receive having
given nothing, ever, and nobody can see whether you have. That single property
is what keeps this a gift rather than an exchange — and it is the reason
everything else is shaped the way it is.

There is no total anywhere. Not per person, not per project, not your own. A
number that can be compared between people is a score, and a score brings back
by social pressure exactly what the code removes.

You can also stop whenever. Taking something on and then stepping away deletes
the record of it entirely: not marked withdrawn, not counted, gone. A stored
record of stopping is a record of not following through, and anything stored
can eventually be counted.

---

## The virtual warehouse

Willing hands are rarely the bottleneck. A pallet of shingles is.

A business or a farm lists a place they keep material, and what is in it. **The
goods never enter our custody** — they stay where their holder keeps them, and
this stores a location, a description and a count. That keeps the platform a
directory rather than a warehouse, which matters legally as much as
practically.

Every amount shows how recently the person holding it last looked: *confirmed
today*, *not confirmed in 4 weeks*. Only the holder can move that clock, and
shipping something out deliberately does not — the sender knows what they sent,
they have not re-counted what is left. Stale listings are dimmed but never
hidden, because they may well still be there.

When material moves, it produces a **manifest** with a QR code. Whoever takes
delivery scans it to sign for it, with no account and no sign-up, because they
are standing in a yard with a phone.

A manifest proves goods **moved**. It states no value, and it never will.

---

## Bills of material

A project can list what it needs — reclaimed oak, 200 board-feet — and people
record what actually arrives. Material can come straight from a warehouse
listing, so the paperwork and the project agree.

**Hours and material are kept in separate logs and are never added together.**
There is no way to record what material is worth, and no way to say what it is
worth in hours. Both would put a price on a gift, and a priced gift is a
transaction.

The one number the system does show is *what is still needed* — 80 board-feet
short. That is a fact about the project, not about any person, and material
cannot be coordinated without it.

---

## Your organization is your own

Each organization is admitted deliberately, and its members, postings, ledger
and material are invisible to every other organization. That separation is
enforced by the database itself rather than by application code remembering to
filter, and it fails closed: a mistake makes rows disappear rather than leak.

Anything that leaves the system — a notification, an email, an integration —
carries only that something exists and a link to it. Never the words somebody
wrote, never a member's name. Those stay behind the boundary and are fetched
when the reader signs in.

---

## How to check any of this

Everything above is a claim, and claims are cheap. So each one is bound to a
test that runs continuously, and the results are published at
**[/attestation/](https://dugnadsand.org/attestation/)** — live, every time you
load the page, so a stalled checker cannot make a green record look like a
green system.

A few of the things checked:

| | |
|---|---|
| `no-gating` | No code path consults what a member has given when deciding what they may receive |
| `no-balance` | No model carries a balance, credit limit, or spendable total |
| `no-material-valuation` | No record of material carries a value, a price, or an equivalence in hours |
| `no-obligation` | Offers are ceilings. Nothing records a minimum, a completion, or a penalty for stopping |
| `no-aggregate-display` | No per-member total is computed or displayed |

A check whose subject does not exist yet reports **incomplete** rather than
passing, and the run as a whole can never read green while any check is in that
state. An honest amber is the right answer until the thing is built.

**This is an engineering manifest, not a legal attestation.** It says what the
code was checked for and what the checks returned. It is not legal advice, it
is not a tax opinion, and it does not tell your organization what its
obligations are. Those are questions for your own counsel and accountant. What
this can tell you is precisely what the software does and does not do, which is
the part we can be held to.

The code is public: **[github.com/ewolters/dugnadsand](https://github.com/ewolters/dugnadsand)**.
The claims are in `policy/manifest.toml`, the checks behind them in
`policy/checks.py`, and the reasoning in `docs/design-rules.md`.

---

Sponsored by [SVEND](https://svend.ai).
