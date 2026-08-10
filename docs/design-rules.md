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

## A note on why these are written down

Every rule here has a plausible feature request attached to it that a thoughtful person
would file. That is what makes them worth recording — not because anyone intends to break
them, but because each one will look, in isolation and on a busy day, like an obvious
improvement.
