# Architecture, against Komunitin

A code-level comparison. Komunitin quotes are from
`github.com/community-exchange-network/komunitin` @ `36d947d` (master, 30 July 2026),
`accounting/` — 13,121 lines of TypeScript.

> **Status note.** Komunitin's code below is shipped and running. Dugnadsand's ledger is
> **not built yet** — the site is live, the record-keeping is not. The Django models here
> are the proposed schema, written out concretely so the comparison is real rather than
> hand-waved. Read them as a spec.
>
> **And expect them to move.** Field names, table shapes and boundaries will change as
> this gets built and as the board, counsel and the first members push back on it.
> Nothing on the dugnadsand side of this document is settled — it is the current best
> sketch, not a commitment. What is *not* expected to move is the small set of
> invariants in [policy/manifest.toml](../policy/manifest.toml), which is precisely why
> those are written as automated checks rather than as prose here: the schema is
> allowed to drift, the properties are not.

---

## The difference, in one artifact

Komunitin's API has this error:

```ts
// accounting/src/utils/error.ts:12, :28
InsufficientBalance = "InsufficientBalance",
...
[KErrorCode.InsufficientBalance]: [400, "Insufficient Balance"],
```

An HTTP 400 meaning *you have not given enough to receive this.*

**Dugnadsand cannot have that error.** Not "has it disabled" — cannot have it, because
there is no quantity in the system that could be insufficient. That is the whole
architectural difference, and everything below is a consequence of it.

---

## Where the gate lives in Komunitin

It is enforced at three layers. This matters, because it is why we did not fork.

### Layer 1 — the schema

```prisma
// accounting/prisma/schema.prisma, model Account
  // These fields need to be updated atomically with ledger updates.
  creditLimit    BigInt
  // creditLimit + balance = ledger balance
  balance        BigInt
  // creditLimit + maximumBalance = ledger trustline limit.
  maximumBalance BigInt?
```

Every account carries a running balance and a floor. The comment is doing real work:
these columns must stay in lockstep with the blockchain, which is why they cannot simply
be ignored.

### Layer 2 — the application check

```ts
// accounting/src/ledger/stellar/account.ts:229-231
async pay(payment: { payeePublicKey: string; amount: string }, keys: {...}) {
    if (Big(this.balance()).lt(payment.amount)) {
      throw insufficientBalance(
        `Payer's balance ${this.balance()} is not sufficient for a payment of ${payment.amount}`)
    }
```

And again for cross-community payments:

```ts
// accounting/src/ledger/stellar/account.ts:276-278
    if (Big(this.balance()).lt(payment.path.sourceAmount)) {
      throw insufficientBalance("Insufficient balance")
    }
```

### Layer 3 — the blockchain itself

Even with both checks removed, the Stellar trustline limit (`creditLimit +
maximumBalance`) would reject the transaction at the network layer, and Komunitin maps
that failure straight back to the same error:

```ts
// accounting/src/ledger/stellar/ledger.ts:461-463
          return insufficientMaximumBalance("Insufficient maximum balance", options)
        ...
          return insufficientBalance("Insufficient balance", options)
```

### Why that means "fork and remove the gating" was never on the table

The property is not a feature flag. It is a column set, two guard clauses, and a
blockchain primitive, and the three are kept consistent on purpose. Removing it means
removing balances; removing balances means removing the ledger; removing the ledger is
most of the 13,121 lines.

That is not a criticism. Komunitin is a **mutual credit currency**, and a currency you
can overdraw without limit is not a currency. They built the right thing for what they
are building.

---

## What replaces it

### Komunitin's unit of record

```prisma
// accounting/prisma/schema.prisma, model Transfer
model Transfer {
  state  String @default("new") @db.VarChar(31)
  amount BigInt
  payerId String
  payer   Account @relation("payer", fields: [payerId], references: [id])
  payeeId String
  payee   Account @relation("payee", fields: [payeeId], references: [id])
  hash String? @db.VarChar(255)
}
```

A transfer has two parties and an amount. Value leaves one balance and arrives in
another. It is a *movement*.

### Dugnadsand's unit of record (proposed)

```python
# site_app/models.py — PROPOSED, not yet built
class Offering(models.Model):
    """Something a member is putting up. Free text on purpose — see design-rules.md §3."""
    member      = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="offerings")
    description = models.TextField()                  # no category, no SKU, no rate
    hours_cap   = models.PositiveIntegerField(null=True, blank=True)  # "up to", never "at least"
    open        = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)


class Claim(models.Model):
    """Someone took what was offered. Note what is absent: no amount, no counterparty
    balance, no settlement. Taking costs nothing and moves nothing."""
    offering   = models.ForeignKey(Offering, on_delete=models.PROTECT, related_name="claims")
    member     = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="claims")
    claimed_at = models.DateTimeField(auto_now_add=True)


class Contribution(models.Model):
    """Hours that were actually given. Attached to the OFFERING, not to a balance.

    There is no `Member.balance` field anywhere in this schema, and that is the
    load-bearing absence. Hours describe work that happened; they are not held.
    """
    offering    = models.ForeignKey(Offering, on_delete=models.PROTECT, related_name="contributions")
    member      = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="contributions")
    hours       = models.DecimalField(max_digits=6, decimal_places=2)
    note        = models.TextField(blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    # Tamper-evidence, not immutability. See §Ledger below.
    prev_hash  = models.CharField(max_length=64, editable=False)
    entry_hash = models.CharField(max_length=64, unique=True, editable=False)
```

There is no `payer`. There is no `amount` that decrements anything. **There is no
`balance` column in the entire schema** — which is why `InsufficientBalance` is not an
error we can express.

An hour is one hour from anyone, so `hours` is a duration, not a price. The moment it
were weighted by skill or denominated in dollars it would become a valuation, and the
gift analysis in [board-case.md](board-case.md) §3 would collapse.

---

## The guard that keeps it true

The claim above — *nothing gates on your record* — is worth exactly as much as its
enforcement. So it is a test, not a policy:

```python
# site_app/tests/test_no_gating.py — PROPOSED
from django.test.utils import CaptureQueriesContext
from django.db import connection

def test_claiming_never_reads_a_contribution_total(client, member, offering):
    """The legal posture of this system is that giving earns you nothing.

    If a claim ever consults Contribution, someone has built eligibility into a
    gift economy. Fail loudly, and make them read design-rules.md §1.
    """
    with CaptureQueriesContext(connection) as ctx:
        client.post(f"/offerings/{offering.id}/claim/")

    touched = " ".join(q["sql"].lower() for q in ctx.captured_queries)
    assert "contribution" not in touched, (
        "The claim path read the contribution ledger. Nothing may gate on what a "
        "member has given — see docs/design-rules.md §1."
    )
```

A member can ask a community running this software to prove the property holds, and the
answer is a passing test rather than a paragraph of intent. That is also why the code is
AGPL: a modified version has to be able to show its source, so the proof travels with the
fork.

---

## Ledger

| | Komunitin | Dugnadsand |
|---|---|---|
| Store | Stellar public blockchain | Postgres, hash-chained |
| Visibility | Public and permanent — *"Every account and every transaction is recorded in the stellar network"* (their docs) | Private to the organization |
| Integrity | Blockchain consensus | `entry_hash = sha256(prev_hash + canonical(row))`, head anchored externally |
| Correct a mistake | Impossible | Possible, and the amendment is visible |
| Honor a deletion request | Impossible | Possible |
| Key material to protect | Stellar sponsor key + per-currency keys + per-account secrets | None |
| Failure mode | Testnet wipe silently loses the ledger (their `STELLAR_NETWORK` defaults to `testnet`) | Ordinary Postgres backups |

The distinction that matters: Komunitin gets tamper-**proof** and pays for it with
permanence. We want tamper-**evident** — an auditor wants to see that nothing was
retroactively rewritten, not to be told a fat-fingered entry can never be corrected.

---

## Size

| | Komunitin `accounting/` | Dugnadsand (projected) |
|---|---|---|
| Lines | 13,121 TypeScript | a few hundred Python |
| Ledger engine | Stellar: trustlines, sponsorship, path payments, sequence numbers, channel accounts, rate-limited Horizon submission | none — nothing is decremented |
| Hard problems inherited | double-spend, atomic DB↔chain commit, credit limits, negative balances, cross-currency path finding | none of them |

Almost every hard problem in Komunitin exists because balances are real and must not be
wrong. When nothing is spent, none of them arise. **The simplicity is not because we are
cleverer; it is because we removed the requirement that generated the complexity.**

---

## Everything else, briefly

| | Komunitin | Dugnadsand |
|---|---|---|
| **Auth** | IntegralCES — Drupal 7 on PHP 7.4, both past end-of-life, outside the main repo and its CI | Django, current, one codebase |
| **Multi-tenancy** | Postgres RLS with `FORCE` on every table — genuinely good, and needed because one deployment serves many currencies | One organization, one database |
| **Marketplace** | Offers and needs with prices; cross-community trade via HOUR assets and path payments | None. Offerings are free text and nobody is matched |
| **Fiat** | Mollie (Europe only), top-up mints currency | None, by design |
| **State machine** | `new → pending → submitted → committed \| failed \| rejected \| deleted` — seven states, because a transfer can fail mid-flight against a blockchain | Two rows appended. Nothing to settle, nothing to fail |

---

## The honest summary

Komunitin is a well-engineered mutual credit currency with a marketplace, built for
European communities that want one. Its balances, its gating, its blockchain and its
seven-state transfer lifecycle are all correct answers to that problem.

We are not building that. We are building a record of gifts, for a US nonprofit that
already gives help without eligibility requirements, and the design constraint that
matters most to us — *nothing may gate on what you have given* — is the one thing
Komunitin's architecture cannot express.

Different problem, different shape. The comparison is only useful because they did their
half well enough to be worth measuring against.
