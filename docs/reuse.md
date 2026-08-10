# What we reused, and what we could not

There is a lot of working software on this box. When dugnadsand needed projects,
the right first question was whether any of it could be layered in rather than
rebuilt. The answer split cleanly in two, and the split is worth writing down
because it will come up again for every feature after this one.

## The platform tier: reuse everything

`kjerne_platform` is a shared library, not an application, and dugnadsand takes
it wholesale:

| What | Used for |
|---|---|
| `notify` | in-app notices and the unread badge |
| `email` | the contact form, via SignalFire → Tempora → Resend |
| `mfa` | TOTP, keyed by email across every federation site |
| `federation_sso` | HMAC assertions for signing in from elsewhere |
| `chain` | the hash chain behind contributions and attestations |
| `middleware` | ops, analytics, brand drift, rate limiting |
| `brand` | `palette()`, `banned_colors()`, the lint that fails the build |

None of this needed adapting. It is infrastructure: it does not have opinions
about what the application means.

**One caveat, and it is load-bearing.** `notify` keys on email address alone and
spans the whole federation by design — a notice raised on one site follows you
wherever you sign in. That is right for the federation and wrong here. An
address that also exists in svend would otherwise see another product's notices
on a mutual aid board, and opening the page would mark them read. Reads are
scoped to `site = 'dugnadsand'` locally, in `site_app/notifications.py`. The
library is correct; the default is simply not ours.

The same caveat applies in the other direction. `notify` writes to the shared
platform database, which Postgres row-level security does not reach. Anything
placed in a notice body has left the tenant. So notices carry the signal — a
need appeared, it is wanted soon — and never free text or a member's name.

## The application tier: reuse nothing

There are at least four project-management models in this estate:

| Where | Model | What it carries |
|---|---|---|
| `~/hoshined` | `hoshin/models/projects.py::Project` | `benefit_type` (Operational / Capex **Savings**), `gl_account`, `financial_category`, `assurance`, `needs_approval`, `approved_by`, budgeted vs actual dates, `owner` |
| `~/svend` | `hoshin/models.py::ActionItem` | `owner_name`, `status` (Not Started → Completed → Blocked), `due_date`, `progress`, `depends_on` |
| `~/kjerne-services` | `Engagement`, `Task` | consulting work with invoicing attached |
| `~/verxted` | `Project` | a portfolio showcase, not project management |

Every one of these is a per-site Django app. None is packaged, so "reuse" would
have meant copying a model, not importing a library — and the copy is where it
falls apart.

These models are good at their job, and their job is to answer **who owes what
by when, and what was it worth.** That is the correct question for a plant
running a savings programme or a consultancy billing an engagement. Dugnadsand
is built so that question cannot be asked:

- `owner` / `owner_name` — assignment is obligation. See `no-obligation`.
- `status` / `progress` — recording a completion records a duty that was owed.
- `benefit_type` / `gl_account` — valuation. See `flat-hours`, `no-tax-artifact`.
- `needs_approval` / `approved_by` — a gate, and gates are what this removes.
- `depends_on` — a dependency is a promise somebody else is holding.

Importing either shape would have breached the manifest on the first migration.
Not because the models are bad, but because the semantics are the exact inverse
of this one's. `site_app/tests/test_projects.py::TheShapeItRefused` asserts each
of those field names is absent, so the answer stays recorded in something that
runs.

## The rule this gives us

**Infrastructure is shared; meaning is not.**

Anything that moves bytes, proves identity, sends mail, hashes a record or
lints a colour belongs in `kjerne_platform` and should be taken from there
without hesitation. Anything that encodes what a row *means* — who is
responsible, what is owed, what it is worth — is specific to the product it
came from, and dugnadsand's meanings are close to the opposite of every other
site in this estate.

The reuse question is therefore never "does this model already exist?" but
"does this model's idea of what it is for survive contact with the manifest?"
For projects it did not, and the replacement is forty lines.
