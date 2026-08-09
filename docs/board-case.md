# A proposal for a mutual aid board

**Prepared by** SVEND · August 2026
**For** the board of a small mutual aid organization
**Subject** Adding a labor-and-goods gift ledger to the organization's existing work

> This is written for a particular kind of organization: one already giving direct
> assistance, already working without eligibility tests, and already funding that work from
> something other than grants. If that is not you, most of the argument below will not
> land. Where it says "you", read your own model into it and correct anything we have
> assumed wrongly — the case depends on getting your model right, not ours.

---

## The short version

You already move money to people who need it, and that machine has a ceiling: **you can
only give away what you take in.** Every dollar of assistance has to be raised or earned
first.

What we are proposing does not raise money. It moves a different resource — hours and
goods that neighbors already have and would give — and keeps a record of it. Somebody
grows more potatoes than they can eat and puts them up. Someone takes them. Nobody pays,
nobody owes, and the hours are written down because the work was real.

It runs under your 501(c)(3), it is already built, and it is sponsored by SVEND at no
cost to the organization.

---

## Why this fits an organization like yours

### 1. It encodes a philosophy you may already operate on

Many small mutual aid organizations describe their work in almost the same words: rapid,
flexible assistance without eligibility requirements, offered on trust. Some take
requests anonymously, so that asking costs nothing and proves nothing.

If that describes you, then what follows is not a value statement we are accommodating.
It is the single hardest architectural constraint in this system, and we built to it
deliberately:

**Nothing in this software gates on what you have given.** There is no path in the code
from a member's contribution record to their eligibility to receive. You can take
without having given. You can take having given nothing, ever.

This matters because it is the thing most systems of this kind get wrong. The obvious
design — everyone earns credits, credits buy help — quietly creates eligibility
requirements and puts people in debt. Ours cannot, because the balance is never
consulted. It is a property we can demonstrate in the code, not a promise in a policy.

Put plainly: an anonymous request form already says that asking should cost nothing and
require nothing. We wrote that same sentence as a test that fails the build.

### 2. It extends your reach without extending your fundraising

Every dollar of assistance you distribute has to be earned first. Labor and goods do not
come out of that budget at all.

Somebody spending a Saturday repairing a neighbor's porch is help delivered that never
touched your bank balance. The two systems are additive: money for what money is needed
for, and this for everything else.

### 3. It protects your exempt status rather than risking it

This is the part we would most want counsel to look at, and the reason we did not simply
adopt an existing platform.

The obvious off-the-shelf option is a *community currency* — members earn transferable
credits and spend them on each other's services. Under US law that design looks a great
deal like a **barter exchange** (IRC §6045(c)(3)), which triggers Form 1099-B reporting,
requires collecting members' Social Security numbers, and puts the organization in the
business of tracking taxable income for everyone who participates.

Our model avoids that by not being an exchange at all. Nothing is transferable, nothing
is owed, and no one gets anything in return for giving. That is a gift, and gifts are not
income to the recipient (IRC §102).

**We are not offering a legal opinion, and the board should not treat this as one.** We
are saying the design was chosen with this question in front of us rather than discovered
afterward, and that it gives your counsel a much easier position to defend.

### 4. The gathering is the point, not the overhead

*Dugnad* is the Norwegian word for a neighborhood doing work together, and the part
Norwegians will tell you actually matters is the coffee afterward. One of the two
photographs on the site is a trail crew stopped for lunch, tools left by the truck. The
sitting-down part counts for as much as the digging.

Organizations that do this well tend to know that already. The software is built so the
record never gets in the way of it.

---

## What we are not claiming

We would rather the board hear the weak points from us.

- **This does not solve money.** People still need rent and gas, and this system will
  never provide either. It sits alongside your existing work; it does not extend it.
- **The free-rider question is real and unsolved.** With nothing gating on
  contribution, what sustains people giving? Our answer is that gift economies run on
  visibility and relationship rather than enforcement — the way open-source software
  does — but that is a community design bet, not a technical guarantee. It is the thing
  most likely to determine whether this works.
- **Liability needs deciding before launch, not after.** Someone on a ladder at someone
  else's house is a real exposure regardless of how the software records it. Our
  recommendation is to categorically exclude licensed trades, work at height, power
  tools, anything involving minors or vulnerable adults, and transportation — and to
  allow skilled trades only through licensed, insured businesses working under their own
  entity. That is a policy the board sets, not a feature we ship.
- **We are early.** There are a few neighbors, a working website, and a long list of
  questions we have not answered.

---

## What we would ask the board to decide

1. **Whether to proceed at all**, under the organization's 501(c)(3).
2. **To engage counsel** on the gift-versus-barter posture before any launch. This has
   the longest lead time of anything here and it can reshape the design, so it should
   start first.
3. **The scope boundaries** — which kinds of help are in and which are out.
4. **Whether hours stay hours.** This is the one technical decision the board should
   own rather than delegate. If a credit is ever denominated in dollars, or weighted so
   that an hour of skilled work counts for more than an hour of unskilled work, the
   system becomes a valued exchange and the analysis in §3 changes. One hour is one
   hour, from anyone, or the protection goes away.

---

## Cost and commitment

The site is live at **dugnadsand.org**, built and hosted by SVEND as a sponsored
contribution. There is no invoice attached to this proposal and no obligation attached
to reading it.

If the board decides against it, nothing is lost. If the board wants to think about it
for a season, that is a reasonable pace for something that depends on neighbors trusting
each other.

---

*Dugnad is the Norwegian word for work a neighborhood does together. Dugnadsånd is the
spirit of it.*
