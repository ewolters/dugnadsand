# Questions for counsel

**Working list, August 2026.** Organised by topic, against how Dugnadsand is
actually built.

This exists to be handed to a tax attorney and a CPA together with
[the statement of operating policy](https://dugnadsand.org/policy/) and
[how it works](https://dugnadsand.org/how-it-works/). The site disclaims being
a substitute for that advice; these are the questions the disclaimer leaves
open.

The crux: the `no-tax-artifact` and `no-material-valuation` design decisions
deliberately push the appraisal and substantiation question onto the
participating organizations and their advisers. That is the thing to evaluate
against actual tax law.

---

## The bind, stated plainly

The feature of nonprofit status that makes large-dollar generosity possible is
the same feature that pulls informal neighbour-to-neighbour systems into a more
scrutinised category the moment somebody with that hat on is involved.

Any mutual aid network that gets organised enough to be trustworthy,
documented and scalable — which is what makes it useful to more than a dozen
neighbours — starts tripping the same wires as a barter exchange or a credit
union, regardless of intent. **Formality and care are the thing being
penalised, not fraud.**

That is a legitimate policy argument and it belongs on the record with counsel,
whatever the answer turns out to be.

---

## 1. Barter and bartering-exchange classification

The IRS defines bartering as an exchange of property or services, and describes
a *barter exchange* as an organization whose members contract to exchange
property or services. It also expressly says the term does not include
arrangements providing solely for informal exchanges of similar services on a
noncommercial basis, such as a neighbourhood babysitting cooperative —
Treas. Reg. §1.6045-1(a)(4).

- Does a system where members exchange labour and material **without a price
  attached** still get treated as a barter exchange — triggering 1099-B filing
  obligations under IRC §6045 — even where the software is built as a gift
  exchange?
- Does the `no-exchange` design (nothing links what a member received to what
  they gave) actually avoid barter-transaction treatment, or does the IRS look
  at the substance of hour-for-hour and material-for-material exchange
  regardless of what the software records?
- Does the degree of platform organization — admin-gated chapters, structured
  postings, cross-organization visibility — risk pulling this out of the
  "informal exchange among neighbours" carve-out and into organised barter
  exchange territory, independent of nothing being priced or credited?

## 2. Volunteer hours and labour

- Are recorded hours simply volunteer labour (not deductible, per longstanding
  rules on volunteer services), or could recording and displaying them under a
  member's name create something closer to a compensation record?
- Does per-member visibility of contributed hours — even without any aggregate
  total — create a reporting obligation for the nonprofit as recipient, or for
  the organization providing the labour?

## 3. Material and in-kind donations

- If the nonprofit deliberately issues **no** written acknowledgment or receipt
  for material received, does that create a problem on its own — recordkeeping
  obligations existing regardless of whether a donor deduction is contemplated
  — or is silence simply fine?
- For a business dispatching material without any receipt or documentation, are
  there consequences on their side purely from removing inventory or supplies
  (basis, cost recovery), independent of any deduction question?
- Is there a risk that a well-meaning member tries to use the transaction log as
  informal deduction support — and if so, should the policy disclaim that
  explicitly everywhere the log is visible?

## 4. Unrelated business income tax

- Does participating as a nonprofit — receiving and giving labour and material
  through a cross-organization platform — create UBIT exposure, particularly
  where some participants are businesses rather than nonprofits?
- Does hosting or administering a chapter create UBIT or private-benefit issues
  where for-profit businesses are members alongside nonprofits and households?

## 5. Private benefit and inurement

*Inurement* is a strict, zero-tolerance rule applying only to insiders —
officers, directors, founders, major donors. Any net benefit to an insider from
the nonprofit's assets or activities is prohibited, full stop, regardless of
amount.

*Private benefit* is broader and applies to anyone. The test is whether the
nonprofit's activities primarily serve its exempt charitable class, or whether
they confer more-than-incidental benefit on private parties — including
for-profit businesses — as a byproduct. It does not require anybody to gain
anything; the concern is whether the nonprofit is in effect donating its
credibility, staff time or resources to help a for-profit business or private
household transact, in a way not clearly in service of its own mission.

- Does facilitating exchanges between nonprofits, businesses and private
  households through one platform risk private benefit or inurement for the
  nonprofit's 501(c)(3) status?
- Is there a risk the IRS views coordinated in-kind giving and receiving among
  mixed entity types as the nonprofit conferring more than incidental benefit on
  for-profit participants?
- Does the nonprofit's role in helping establish and promote a shared platform —
  used by non-charitable entities as much as by itself — constitute
  more-than-incidental private benefit to those participants, even though the
  nonprofit gains nothing and controls nothing? **Does it matter that nobody
  owns the platform at all?**

## 6. The relationship with SVEND

Neither entity can profit, nobody owns Dugnadsand, and the shared goal is
explicitly to make both organizations less necessary as facilitators. This is
not a fiscal sponsorship or a joint venture in the classic revenue-sharing
sense. The sharper questions:

- Given that no money or ownership is involved, does any formal agreement serve
  a real purpose — or is the risk purely about liability allocation (software
  failure, a data breach, a bad-faith listing) rather than tax
  characterisation?
- Does "sponsored by SVEND" language need review so it cannot be read as an
  endorsement, an in-kind benefit, or an informal joint venture requiring
  disclosure on Form 990 (Schedule R, related organizations)?
- With no revenue at all, is there any circumstance in which this is a "trade or
  business regularly carried on" for UBIT purposes, or does the absence of a
  profit motive and of any exchange of value take that off the table?

## 7. Entity and liability structure

- Should Dugnadsand, or a local chapter, be a separate legal entity — or does
  operating under a nonprofit's umbrella expose that nonprofit to liability for
  a system it does not fully control (data governance, material moving without
  custody or insurance)?
- Since the platform takes no custody and disclaims warehouse and insurance
  functions, does the nonprofit — or the founder personally — carry liability if
  donated material is misrepresented, damaged or disputed?

## 8. State and local

Scope is Upstate SC only for now.

- Do South Carolina or North Carolina treat labour/material time-banking or
  mutual-aid networks differently for sales tax, use tax, or charitable
  solicitation registration?
- Does operating across two states — Upstate SC and Western North Carolina —
  trigger separate registration or reporting?
- What should be documented or structured **now**, while this is one state, to
  make a second-state chapter straightforward rather than a re-litigation of all
  of the above?

## 9. Recordkeeping

- Given that the platform is deliberately built to avoid producing tax
  artifacts, what records should the nonprofit maintain **independently** to stay
  compliant, since it cannot rely on the platform's exports for substantiation?

See the appendix for exactly what the system does and does not record.

---

## 10. Variance power — the load-bearing question

If a nonprofit fiscally sponsors Dugnadsand or a chapter, the sponsor must
retain full legal discretion over funds. A donor cannot direct money to a
specific chapter or project as though the sponsor were a pass-through; that
makes the sponsor a conduit, and conduit arrangements are not deductible —
Rev. Rul. 68-489 and Rev. Rul. 66-79.

The two models that square this:

**Model A — the project stays inside the sponsor.** The chapter is not a
separate recipient at all; legally it is a programme of the sponsor. No
selection happens because there is no separate entity to select.

**Model C — a pre-approved grant relationship.** The chapter is separate and
independent. The donor gives to the sponsor; the sponsor has legal discretion
over who receives grants and chooses to grant to the chapter, using expenditure
responsibility to confirm charitable use. A donor's stated preference is a
non-binding recommendation, as with a donor-advised fund. If the sponsor were
legally bound to honour it, that is the conduit problem again.

**Put almost verbatim to counsel:** if a nonprofit fiscally sponsors Dugnadsand
or a specific chapter, what does *real discretion* need to look like in practice
for the arrangement to survive scrutiny — and **is a sponsor that never actually
says no to a chapter's request still exercising the discretion the law
requires?**

---

## 11. Stewardship, and the range of options

- What is the minimum structural separation needed to remove a nonprofit from
  Dugnadsand's inurement and private-benefit exposure, short of its executive
  director stepping down?
- Does a formal fiscal sponsorship arrangement — as opposed to informal
  "sponsorship" language on a website — better protect both parties by putting
  money and liability in a defined, accountable relationship rather than an
  ambiguous one?

There is a wide range between "run Dugnadsand as ED of the nonprofit" and "quit
the nonprofit to run it as a private citizen". The realistic options worth
putting to the attorney:

1. The board formally acknowledges Dugnadsand as **not** a programme or
   initiative of the nonprofit; participation is in a personal capacity,
   disclosed to the board, with a clear wall between the two. Officers sit on
   unrelated community boards routinely, and this may resolve the exposure
   without anybody giving up a role.
2. Dugnadsand becomes genuinely separate — its own unincorporated association or
   unaffiliated project, the way Food Not Bombs chapters are — with the
   nonprofit not named as founder or sponsor anywhere on the site.
3. The ED stays, and Dugnadsand is structured so the nonprofit is never a party:
   no branding, no resources, no board minutes referencing it. That is different
   from resigning.
4. Somebody decides Dugnadsand matters more than the role. A legitimate answer —
   but a decision about a life and a vocation, not a workaround for a
   tax-structure problem, and it deserves to be made on those terms.

---

## The structural irony, for the record

This system is engineered so that no person can be a bottleneck: no gating, no
admin approval of who receives, nobody's name required on anything in order to
participate.

The one part that still runs through a bottleneck is the legal structure itself,
because somebody has to be the accountable party if a nonprofit is involved at
all.

The tax code has no category for *a person who wants to help without being the
chokepoint*. It has categories for entities and for the people who control them.
So the thing this was designed to eliminate on the giving side is reintroduced
on the legal-liability side, and it cannot be structured away without either
separating the nonprofit out entirely or accepting a named human the law will
look at.

Fiscal sponsorship with genuine variance power, and full separation with no
nonprofit branding, are the two tools on the table that actually remove that
person as the point of legal accountability rather than papering over it.

---

# Appendix — what the system actually records

*Generated from the models and the manifest, not from the prose. Counsel should
evaluate this rather than the description of it.*

## The eleven commitments

Each is bound to a named check that runs against the source code. Results are
published at <https://dugnadsand.org/attestation/>, computed at the moment the
page is drawn, so a stalled checker cannot present a stored pass as a current
one.

| Name | Commitment |
|---|---|
| `no-balance` | No member holds a balance, credit limit, or any spendable quantity. |
| `no-gating` | No code path consults what a member has given when deciding what they may receive. |
| `no-routing-by-record` | No code path consults what a member has given when deciding who to tell about a need. |
| `no-material-valuation` | No record of material carries a value, a price, or an equivalence in hours. |
| `no-exchange` | Nothing links what a member received to what a member gave. |
| `flat-hours` | An hour counts as one hour, from anyone, and is never denominated in money. |
| `no-money-rails` | The system integrates no payment processor and moves no funds. |
| `no-tax-artifact` | The system emits no per-member valuation, total, or statement that could function as tax substantiation. |
| `no-catalog` | Postings are free text. No categories, rates, or suggested values. |
| `no-obligation` | An offer of time is a ceiling with no floor, and stopping is recorded nowhere. |
| `no-aggregate-display` | Nothing computes or displays a per-member total of contributed hours. |

## Fields stored, per record type

Every table carries an owning organization, and none carries anything naming
money.

| Record | What is stored |
|---|---|
| **Contribution** — an hour given | member, posting, `hours` (decimal), free-text note, timestamp, and a hash chaining it to the previous entry |
| **Claim** — taking something on | posting, member, timestamp. Stepping off **deletes the row**: no record of withdrawal survives |
| **Posting** | member, kind (asking / offering / just saying), free-text description, optional `hours_cap` ceiling, optional `needed_by` date |
| **StockLine** — material on a shelf | warehouse, free-text description, quantity, unit, who last confirmed it and when |
| **Manifest** — material dispatched | source line, quantity, free-text destination, who sent it, when, whether it was signed for, and a single-use receipt token |
| **MaterialNeed / MaterialGiven** | project, description, quantity, unit, who, when |
| **Measure** — an outcome | project, label, quantity, unit; typed by a person and never computed from the ledger |
| **Interest** | posting, member, optional `hours` ceiling |

## What is absent, and enforced as absent

- **No monetary value anywhere.** No field on any material-bearing record may
  name a value, price, cost, worth, amount, appraisal, fair market, retail or
  rate. A check walks the models and fails on a match.
- **No link between what a member received and what they gave.** Any record
  carrying two member references trips `no-exchange`. This refused a legitimate
  design during development and the field was dropped rather than the check
  waived.
- **No per-member total, at any level.** Not per member, not per project. The
  check scans the application source *and* the templates for aggregation over
  contributions.
- **No hours-to-material equivalence.** The two records are kept apart and never
  added; a relation from a material record to the hours ledger fails the same
  check as a price field would.
- **No payment processor, and no funds movement.**
- **No document that could function as substantiation.** The impact packet — the
  one artifact sent to somebody who gave something — states in terms that it is
  not a receipt or a valuation and cannot support a deduction.

## What evidence therefore exists

For **labour**: a per-entry log of who gave how many hours toward which posting,
on what date, in a hash chain where each entry commits to its predecessor.
Tamper-evident rather than tamper-proof, deliberately, so an organization can
correct an error or honour a deletion request.

For **material**: that a described quantity moved from a named place to a named
destination on a date, and whether the recipient signed for it. Never what it
was worth.

There is **no export, report or statement** that totals anything, values
anything, or attributes a figure to a person. Anything a nonprofit needs for
substantiation must be maintained independently of this system — which is the
subject of question 9.

