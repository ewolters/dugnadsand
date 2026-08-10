# The virtual warehouse, and bills of material

The bottleneck in mutual aid is rarely willing hands. It is a pallet of shingles,
a run of pipe, forty sheets of plywood. Somebody nearby usually has them already.

These two features are about that, and both are shaped mostly by what they
refuse to record.

---

## The warehouse: an index of other people's barns

A business or a farm keeps material somewhere. They list the place, and what is
in it. That is all.

**Nothing enters our custody.** The goods stay where their holder keeps them,
and this stores a location, a description and a count. That is not modesty, it
is the whole legal shape:

> no custody → no title → no storage liability, no insurance obligation, no
> unrelated-business exposure

The platform stays a **directory**, which is exactly the posture that keeps
hours a **record** rather than a currency. One sentence covers both halves of
the system:

**We prove a thing moved. We never say what it was worth.**

So `Warehouse` is an address and somebody to ask. There is no capacity field,
no utilisation, no cost per pallet. Anything that would make it a warehouse
management system would also make it something that manages other people's
property, which is the thing it must not be.

### Staleness is never allowed to read as availability

A quantity with no date attached is a claim about the present tense that nobody
checked — and somebody drives forty miles on it.

So every stock line carries when its holder last confirmed it, and every
surface that shows an amount shows how old that confirmation is. Not as a
date to do arithmetic on, as a judgement: *confirmed today*, *confirmed 5 days
ago*, *not confirmed in 4 weeks*, *not confirmed in months*.

Two rules keep that honest:

- **Only the holder moves the clock.** Anyone else asserting what is in
  somebody's barn is guessing.
- **Sending material does not refresh it.** The sender knows what they sent;
  they have not re-counted what is left. Letting a shipment reset the clock
  would make the shelf look freshly checked *because something left it*.

Stale stock is dimmed but never hidden. It may still be there, and dropping it
silently would be worse than showing it late.

### Signing for it

Material moving out produces a **manifest**: what, how much, from where, to
whom, when. It carries a QR code and no valuation.

The QR is a single-use link that needs no account, because whoever takes
delivery is standing in a yard with a phone. Requiring them to sign up means
the receipt never gets recorded — and an unrecorded receipt is the thing a
donating business needed this for in the first place. Scanning it twice is a
no-op rather than an error, because a QR gets scanned twice by two people on a
loading dock and an error message helps nobody there.

A manifest is **evidence of transfer**. A valuation is a different document,
and only one of the two is safe for a platform to produce.

---

## Bills of material: what a project needs

A project can carry a list of what it needs — reclaimed oak, 200 board-feet —
and people record what actually arrives against it. Material can be shipped
straight from a warehouse onto a line, so the manifest and the project tell one
story.

### The conversion that is not built

The sentence that always follows *"let's attach a bill of materials"* is:

> "…and the material just becomes the hours that went into making it, or an
> estimate."

Both halves of that end the model, and it is worth being exact about why.

**An estimate** of donated property is an appraisal — produced by a platform,
about a donor, of a gift the donor may deduct. That is the single most
dangerous artifact this system could emit, and it is not made safe by calling
it a rough figure.

**An equivalence in hours** — *200 board-feet became 40 hours* — reads like
bookkeeping and is an exchange rate. A rate is ascertainable value however it
is denominated. Once timber and time are commensurable, the gift framing is
gone and what is left is a barter exchange with extra steps.

So a project keeps **two logs, adjacent and never summed**, and the page says
so in words rather than leaving it to be inferred. No function converts between
them, and the policy check fails on a database relation to the hours ledger as
readily as on a field called `value` — because that conversion arrives as a
foreign key at least as often as a number.

### The aggregate that is allowed

*80 board-feet still needed.*

That is an aggregate over the **need**, not over a person. It is a fact about
what the project still wants, and material cannot be coordinated without it.

A per-member material total is the forbidden one, for exactly the reason a
per-member hours total is: a number that can be compared between people is a
score, and a score reintroduces by social pressure what the code removed.

Individual gifts appear in a log, as hours do. Nothing computes anybody's sum.

### Over-delivery is recorded, not clamped

Somebody turning up with more than was asked for is a good day. A log that
trimmed it would have stopped describing what happened in order to keep a
number tidy.

---

## Where this is enforced

`policy/manifest.toml` carries an invariant, `no-material-valuation`, checked
on every run and published at [/attestation/](https://dugnadsand.org/attestation/):

> No record of material carries a value, a price, or an equivalence in hours.

The check scans every material model for value-shaped field names *and* for any
relation to the contribution ledger. It has been verified by planting both — a
field called `estimated_value` and a foreign key called `counted_as` — and it
caught each one, naming the field.

That is the difference between a policy and a property. The claim above is not
a promise about intent; it is a thing the build fails without.
