# Governance — who decides what

**Draft for a decision, 14 August 2026.** This exists so the question is about
something specific rather than about whether a board feels necessary.

It describes three layers, says which decisions sit in each, and is honest
about which ones a board can actually take off the operator and which it
cannot.

---

## The distinction that matters

**An advisory board advises. A governing board decides.**

Only the second takes anything off you. An advisory board with no delegated
authority leaves every decision where it is and adds meetings — which is worth
saying plainly, because "we should have a board" usually means the first and
is hoped to do the work of the second.

Nothing below assumes a legal entity. Two of the three layers already exist in
the code; what is missing is the top one, and what is missing from the top one
is authority rather than people.

---

## Layer 1 — the operator

**Today: Eric, personally, and SVEND.**

This is the layer that cannot be delegated by writing a document, because it is
defined by who is on the hook:

| Decision | Why it stays here |
|---|---|
| Whether the service runs at all | Hosting, domain, database, backups are held by one person |
| What the terms say | The indemnity runs *to* the operator; the operator is the counterparty |
| Responding to legal process | Whoever is served is served |
| Breach notification | The obligation attaches to whoever holds the data |
| Spending money on it | There is no treasury |

A board does not move any of these unless it comes with an entity that holds
the assets and the contracts. **That is the real question underneath "do we
need a board": not who advises, but who is the operator.** See
`docs/for-counsel.md` §7 and §13.

## Layer 2 — chapter officers

**Today: `RegionRole`, roles `lead` and `admin`. Eric and Hannah, Upstate SC
and Western North Carolina.**

This layer exists in the code and already decides things:

| Decision | Where |
|---|---|
| Admit an organization | `/chapter/application/<id>/` |
| Decline one | Same, with a note kept and not sent |
| Remove an organization from the chapter | `/chapter/` — reason required and recorded |
| Look at a credential and record that they did | Optional; gates nothing |

Two properties are already true and worth keeping: the permission is by region
id rather than by "is an officer somewhere", and holding a role grants no view
of anybody's records. An officer who is also a member sees what every other
member sees and no more.

**What this layer cannot do today:** anything network-wide. There is no way to
change a policy, admit a chapter, or settle a dispute between two chapters,
because there is nowhere for that to happen.

## Layer 3 — a board of trustees

**Does not exist. This is the thing to decide about.**

If it existed, the defensible set of decisions to give it:

| Decision | Currently |
|---|---|
| Approve a new chapter and its officers | Nobody; regions are created by hand |
| Amend the acceptable use policy | Eric, by editing a template |
| Amend the terms | Eric, and it is a contract |
| Hear an appeal against a removal | Nowhere. A removed organization has no recourse |
| Decide what counts as a mutual aid group | Eric, by setting `Organization.kind` |
| Decide whether the network continues | Eric |

The fourth row is the strongest argument for it. Removal is currently final,
unilateral, and reviewed by nobody — an officer removes an organization with a
reason recorded, and that is the end of it. That is a real gap in fairness and
it is not about anybody's feelings.

The fifth row is the second strongest. Who counts as a mutual aid group decides
who can see a request from somebody asking for help. That is the most
consequential switch in the system and one person flips it.

---

## What a board would and would not fix

**Would.** Decisions stop being *Eric decided*. Disagreeing with an admission,
a removal or a policy becomes disagreeing with a process, which is different in
kind and is the reason organizations invent roles at all. It also gives a
removed organization somewhere to go, which is a fairness gap today regardless
of who is involved.

**Would not.** It does not reduce liability. The operator is still the operator,
and a board without an entity behind it is a group of people whose advice the
operator took. It does not make anybody less upset either — structure makes
decisions less personal, not less painful, and a board created mainly so a
specific dynamic has somewhere to go will disappoint on exactly that.

---

## Three options, smallest first

**A. Nothing.** Keep chapter officers, accept that network-wide decisions are
the operator's. Honest for a network of two organizations. Costs nothing and
leaves the removal-appeal gap open.

**B. A written delegation, no entity.** A named group with authority over the
rows in Layer 3, recorded in a document and referenced from the terms. Real
authority over policy and appeals; no effect on liability. Roughly a day of
work: a `docs/governance.md` that is normative rather than a draft, a page at
`/governance/`, and a `RegionRole`-shaped model one level up.

**C. An entity with a board.** The nonprofit or LLC that `for-counsel.md` §7
asks about, holding the assets, the contracts and the insurance, with a board
that appoints the operator. This is the only option that moves Layer 1. It is
also the one that needs a lawyer, a filing and a bank account.

**B is not a step toward C.** They solve different problems: B distributes
decisions, C moves liability. Doing B does not make C easier, and doing C makes
B a formality. If the reason for asking is liability, only C is responsive; if
it is that decisions should not all be one person's, B is enough.

---

## What would have to be built for B

Small, and none of it speculative:

- A model beside `RegionRole` for a network-level role, with the same property:
  attached to a login, no relation to any tenant-scoped record in either
  direction, no view of anybody's records.
- An appeal route from a removal. `ChapterRemoval` already records who, why and
  when; it has nowhere to be contested.
- A version on the acceptable use policy, the way the terms already carry one,
  so "the board approved version 3" means something.
- A public `/governance/` page saying who holds what, in the register the other
  documents use.

## What would have to be decided first

- Who is on it, and how somebody stops being on it.
- Whether a member organization can appeal to it, or only a removed one.
- Whether it can overrule a chapter officer, or only review after the fact.
- What happens when it deadlocks.

None of those are code questions.
