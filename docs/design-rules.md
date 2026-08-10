# Design rules

These are not style preferences. Each one holds up part of the legal and social posture
described in [board-case.md](board-case.md) and [komunitin-comparison.md](komunitin-comparison.md).
They are written down because they will each look, at some point, like a small helpful
feature worth adding — and every one of them erodes by good intentions rather than by
malice.

---

## 1. Nothing gates on the record

**Rule:** no code path may read a member's contribution total to decide what they may
receive.

**Why:** the moment the record confers advantage it becomes consideration, and a system
where giving earns you something is an exchange. It also destroys *assistance without
eligibility requirements*, which is the operating philosophy this was built to serve.

**How to hold it:** this is testable. Assert that the claim path never queries the
contribution total, and keep the assertion in CI. A passing test is a better artifact
than a paragraph of intent — it stays true after everyone has forgotten why it was
written.

**What breaks it:** priority access for high contributors. Sorting a list by hours.
A nudge that says "you've received four times and given once." Any of these, shipped by
someone reasonable trying to be helpful.

**And the quiet version — routing.** Once the system started telling people that a need
exists, a second surface opened. "Send needs to whoever actually turns up" is the
obvious efficiency win, it reads as good engineering, and it is this rule broken: a
member who has given nothing hears about fewer needs, so the record has begun deciding
what reaches whom. Withholding the chance to help is a softer denial than refusing a
claim and it is still a denial. Everyone in the organization hears; who responds is
theirs to decide. Enforced separately as `no-routing-by-record`, because the check
behind rule 1 scans claim paths and cannot see delivery ones.

---

## 2. Hours are hours

**Rule:** one hour counts as one hour, from anyone, for anything. Never weighted by
skill, never denominated in dollars.

**Why:** an hour of legal advice worth three hours of weeding is a price. A price is a
readily ascertainable fair market value, and that is the fact a barter exchange
determination turns on. Flat hours carry no valuation.

**What breaks it:** "shouldn't a plumber's hour count for more?" It is a fair question
and the answer has to be no.

---

## 3. No catalog, no categories, no suggested rates

**Rule:** offerings are free text, written by the person offering. No service taxonomy,
no dropdown of common tasks, no "typical hours for this kind of job."

**Why:** standardized categories create comparables, and comparables create ascertainable
value. A list of suggested hours is a price list wearing a helper's hat.

**What breaks it:** search filters that need categories to work. Analytics that need
buckets to chart. Both are real product pressures.

---

## 4. Up to, never at least

**Rule:** an offer of time is a ceiling with no floor. A member may stop at any point,
for any reason, with no consequence recorded anywhere.

**Why:** no obligation means no bargained-for exchange, which supports the gift framing,
and it is strong evidence against employment classification. The absence of a remedy is
the feature.

**What breaks it:** a reliability score. A "completed / abandoned" flag. Anything that
makes stopping cost something, even socially.

---

### Stopping has to be operable, and it has to leave nothing

"You can stop whenever" was a sentence in this document with no button behind it
for as long as there was no way to step off a claim. There is one now, and the
important half is the second one: stepping off **deletes the row**.

The responsible-looking implementation is a `withdrawn` flag or a
`stepped_off_at` timestamp, because keeping history is normally the correct
instinct. Here it is the harmful one. A stored record of stopping is a record of
not following through; anything stored can be counted; "Ada has stepped off four
times" is a reliability score; a reliability score is standing. `no-obligation`
forbids those field names outright and
`test_no_field_anywhere_could_record_that_somebody_stopped` asserts it.

Hours already given survive, because a `Contribution` points at the posting and
never at the claim. Work that happened is a fact about the world rather than a
commitment anybody made.

The poster is told — silence would be its own harm if your driver quietly
stepped off — but only when the **last** person leaves, and as a state rather
than an event: "nobody is on this at the moment", never "somebody stepped off".
An event has a subject, and a notice whose subject is a person who stopped is a
notice that they let you down.

---

## 5. Recognition, not advertising

**Rule:** a business that contributes is acknowledged by name and logo only. No
qualitative claims, no pricing, no calls to action, no contact-for-hire link.

**Why:** IRC §513(i) treats a value-neutral acknowledgment as *not* advertising and *not*
a quid pro quo. Cross that line and the nonprofit picks up unrelated business taxable
income and the donors' deductions erode.

**How to hold it:** this is a template constraint. The contribution display either
renders a name and an hour count, or it renders a business listing. Whoever writes that
template eighteen months from now decides which.

---

## 6. The platform stays out of the commercial path

**Rule:** no referrals, no matching for paid work, no facilitation of transactions.

**Why:** members hiring a contributor for paid work later is ordinary life and cannot be
prevented. What matters is that the organization is not the broker.

---

## 7. Skilled work goes through licensed, insured businesses

**Rule:** trades requiring a license are offered only by businesses operating under their
own entity, with an active license and a certificate of insurance on file.

**Why:** this is the exception that lets the ecosystem do *more*, not less. A licensed
electrician working under their own insured entity removes the licensing exposure, the
insurance gap, and the employment question all at once.

**Note on verification:** check objective, verifiable facts — is the license active, is
there a COI on file. Do not attempt subjective vetting of individuals' character or
competence; screening people and having one slip through creates a duty that not
screening never had.

---

## 8. The ledger is private and amendable

**Rule:** records live in the organization's own database, hash-chained so tampering is
detectable, with the head hash anchored externally. Not on a public blockchain.

**Why:** tamper-*evidence* is what an auditor wants. Tamper-*proof* is what you are stuck
with — you cannot correct a mistake, honor a deletion request, or unwind a record made
under duress. In a small community a public transaction graph is de-anonymizable by
amount and timing.

---

## 9. Material is described and counted, never priced

**Rule:** no record of material may carry a value, a price, or an equivalence
in hours.

**Why:** two conversions will be proposed, both will sound like improvements,
and both end the gift framing.

A **price** on donated material makes this an appraisal of donated property —
produced by a platform, about a donor. That is the artifact a §170 deduction
turns on, and the one document a system like this must never generate. A
manifest may prove goods *moved*. What they were worth is between the donor,
their advisor and the IRS.

An **equivalence in hours** — "200 board-feet became 40 hours" — reads as
bookkeeping and is an exchange rate. A rate is ascertainable value however it
is denominated, and once material and labour are commensurable, rule 1 and
rule 2 are both gone. Two logs, deliberately never summed.

**How to hold it:** `no-material-valuation` in the manifest scans every
material model for value-ish field names *and* for any relation to the hours
ledger, because the equivalence can arrive as a foreign key as easily as a
number.

---

## 10. Two logs, never summed

**Rule:** a project records hours and material in separate logs, and nothing
converts between them.

**Why:** the sentence that always follows "let's attach a bill of materials" is
*"and the material just becomes the hours that went into making it, or an
estimate."* Both halves end the model.

An **estimate** of donated property is a §170 appraisal — produced by a
platform, about a donor. An **equivalence in hours** is an exchange rate
however it is denominated, and once material and labour are commensurable there
is a price on both, which is rule 1 and rule 9 gone together.

**How to hold it:** `no-material-valuation` fails on a relation to
`Contribution` as readily as on a field called `value`, because the conversion
arrives as a foreign key at least as often as a number. The project page states
the separation in words rather than leaving it to be inferred.

**What is allowed:** *what is still needed.* That is an aggregate over the
**need**, not over a person — 80 board-feet still wanted is a fact about the
project's requirement. Material cannot be coordinated without it. A per-member
material total is the forbidden one, for the same reason a per-member hours
total is.

---

## 11. We never take custody

**Rule:** goods stay where their holder keeps them. The system records a
location, a description and a count.

**Why:** no custody means no title, and no title means no storage liability, no
insurance obligation and no unrelated-business exposure. The platform stays a
*directory* — which is exactly the posture that keeps hours a *record* rather
than a currency. One sentence covers both: **we prove a thing moved, we never
say what it was worth.**

**And the operational half:** a quantity with no date is a claim about the
present tense that nobody checked, and somebody drives forty miles on it. Every
surface showing an amount shows how old the confirmation is, only the holder
can move that clock, and **staleness never renders as availability**. Stale
stock is dimmed, never hidden — it may still be there, and dropping it silently
would be worse than showing it late.

---

## 12. No like, and nothing that counts approval

**Rule:** nothing records or displays a reaction, a vote, a rating or a count
of who approved of something.

**Why:** a like count is a public number attached to a person's contribution,
which is a score wearing a warmer word. Once posts carry visible counts people
write for the counts, and whoever gives quietly ranks below whoever posts well.
That is rule 1 defeated by social pressure rather than by code — which is the
harder version to undo, because no line of it is wrong.

**What replaces it:** *thanks*, which is sent and gone. It is deliberately
**not a model**. That began as a schema problem — a row with a sender and a
recipient has two foreign keys to `Member`, which `no-exchange` flags on sight
because a two-party record is how a transfer looks — and the honest fix turned
out to be better than the feature it replaced. With nothing stored, "never
counted, never aggregated" stops being a promise about restraint and becomes a
fact about the schema. Nobody can total what was never written down.

**Pins are private.** A public pin is editorial ranking: the same problem with
an editor, where attention is decided by whoever pins rather than by whoever
needs.

---

## 13. The system pairs facts. People pair people.

**Rule:** a pairing utility may join two *records*. It may never rank, score,
or narrow *people*.

**Why:** matching a need to stock in the same unit is coordination. Ranking
members by suitability is scoring, and the moment such a ranking consults what
somebody has given it is rule 1 broken — quietly, in the one place nobody
thinks to look, because it arrives as a helpful feature.

**How to hold it:** none of `running_out`, `fillable_needs` or `going_quiet`
takes a member argument, and a test asserts that. If one of them ever needs to
know who is asking in order to decide what to surface, it has stopped being
coordination, and that change would begin by adding exactly that parameter.

Material is matched on **unit**, never on description. A unit is a word a
member typed; matching equal ones compares two facts. Matching descriptions
would need a vocabulary of materials to compare against — and a vocabulary
makes two donations comparable, which is rule 3. If this ever needs to be
cleverer, the answer is a better search box for a person, not a better
classifier for a machine.

**Where a person should be asked, a person asks them.** That is `invite()`, and
the sender never learns what came of it.

---

## A note on why these are written down

Every rule here has a plausible feature request attached to it that a thoughtful person
would file. That is what makes them worth recording — not because anyone intends to break
them, but because each one will look, in isolation and on a busy day, like an obvious
improvement.
