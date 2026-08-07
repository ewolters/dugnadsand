# Why not Komunitin

Komunitin is the most credible open-source platform in this space, and it was the
starting point for this work. We reviewed it in detail before deciding to build
something else. This document records what we found and why we went a different way.

**Reviewed:** `github.com/community-exchange-network/komunitin` @ `36d947d`
(master, 30 July 2026), plus its runtime dependency IntegralCES.
**Method:** source review. No live testing, no penetration testing.

---

## First, credit where it is due

Komunitin's accounting service is well built. Specifically, and verified from source:

- Secrets encrypted with **AES-256-GCM**, fresh random IV per operation, auth tag stored
- A **three-tier key hierarchy** — operator master password → HKDF-SHA512 → per-currency
  key → individual ledger account secrets, so one currency's compromise doesn't cascade
- **Postgres row-level security** with `ENABLE` *and* `FORCE` on every table, so tenant
  isolation is enforced by the database rather than by application code
- A disciplined RLS bypass used in exactly one place in the entire codebase
- A CI job that tests **backup restores**, which is rare at any size

The maintainers know what they are doing. Nothing below is a criticism of their
engineering. It is a statement that the system solves a different problem, in a
different legal environment, than the one in front of us.

---

## The three reasons we did not adopt it

### 1. It is a currency, and we do not want a currency

This is the substantive one; the others are consequences.

Komunitin implements **mutual credit**. Members hold balances, balances are
transferable, and members trade with each other through a marketplace of offers and
needs. Their own documentation describes each community as issuing its own asset with a
defined exchange rate.

Under US law that shape is close to the statutory definition of a **barter exchange**
(IRC §6045(c)(3)) — an organization whose members contract to trade goods and services,
explicitly including systems operating through credits rather than direct swaps. That
brings Form 1099-B reporting and TIN collection for participating members, and it makes
the operating nonprofit responsible for tracking taxable income on their behalf.

Our design removes the trigger rather than managing it. Contributions are recorded but
not transferable and not owed. Nobody receives anything in exchange for giving, so
there is no exchange to report.

A second consequence follows from the same choice. Because balances are a claim,
Komunitin necessarily gates on them — you cannot spend what you have not earned. For an
organization whose stated approach is *assistance without eligibility requirements*,
that is not a setting to be turned off. It is what the software is.

### 2. Authentication runs on end-of-life software

Every login, password and API token in Komunitin is issued by **IntegralCES**, a
**Drupal 7** application on **PHP 7.4**. Drupal 7 stopped receiving security advisories
on 5 January 2025; PHP 7.4 stopped on 28 November 2022. This component is not in the
main repository and is not covered by its CI, and its drupal.org page states there are
no supported stable releases.

The build also disables Composer's insecure-package blocking outright
(`composer global config audit.block-insecure false`) and downloads Drupal core unpinned
at build time.

Adopting Komunitin means either operating an EOL CMS as the front door to member data,
buying commercial extended support for it, or waiting on the replacement auth service the
project has scaffolded but not built. For a small nonprofit with no security staff, none
of those is a good position.

### 3. Every transaction is published to a public blockchain

Komunitin records each account and each transfer on the **Stellar public network**. Their
documentation is explicit: *"Every account and every transaction is recorded in the
stellar network."*

For a small pilot this is a privacy problem rather than a feature. With a small
membership, a permanently public transaction graph can be de-anonymized by correlating
amounts and timing — a participant's employer or neighbor could read their entire history
in the system. Those records cannot be deleted, which sits badly against any deletion
right the organization promises members.

There is a fourth, smaller point: the only fiat integration is **Mollie**, a European
payment processor that will not serve a US operator. That mattered less once we decided
no money would enter the system at all.

---

## Side by side

| | Komunitin | Dugnadsand |
|---|---|---|
| **Unit** | Transferable currency, per-community asset | Non-transferable record of hours given |
| **Can it be spent?** | Yes — that is the point | No |
| **Gating** | Balance limits what you can receive | Nothing gates on the record |
| **Marketplace** | Offers and needs with prices | None |
| **US tax shape** | Resembles a barter exchange (1099-B, TINs) | Gift (IRC §102); no exchange to report |
| **Money transmission** | Live question once fiat enters | Not triggered — no fiat |
| **Ledger** | Public Stellar blockchain, permanent | Private Postgres, hash-chained, amendable |
| **Auth** | Drupal 7 / PHP 7.4 (both EOL) | Django, current |
| **Fiat rail** | Mollie (Europe only) | None by design |
| **Deletion / correction** | Impossible on-chain | Possible, with tamper-evidence |

---

## What we kept

Two things, both ideas rather than code:

**Hours as the unit.** Komunitin's inter-community trade unit is called HOUR, and their
external accounts trade in it. They arrived at hours for their own reasons; we use hours
because an hour valued the same regardless of who gives it carries no market price, which
is what keeps the record from being a valuation.

**The seriousness of the ledger.** Komunitin treats the record as something that must be
correct, tamper-evident, and reconcilable. We agree. We simply hold that a hash-chained
append-only table achieves that without publishing anyone's life to a global blockchain.

---

## Honest limits of this review

- Source review only. No live or penetration testing was performed.
- IntegralCES was reviewed at the build and packaging level, not line by line.
- No operator's deployed configuration was examined; several findings are mitigable by
  deployment choices not visible from the repository.
- The tax and regulatory framing throughout is **not legal advice** and requires review
  by counsel licensed in South Carolina.

None of the above should be read as a recommendation against Komunitin for the
communities it was built for. In Europe, with a mutual-credit currency as the goal, it
is a reasonable choice. We are building something else.
