# Dugnadsand

*Dugnad* is the Norwegian word for work a neighborhood does together — the Saturday the
whole street turns out to clear the lot or paint the community hall, and nobody keeps
track of who owed what. *Dugnadsånd* is the spirit of it.

This is the site and, in time, the record-keeping for mutual aid organizations in
upstate South Carolina. It is multi-tenant: each organization is admitted deliberately,
and row-level security keeps every organization's members, offerings and ledger
invisible to the others. Sponsored by [SVEND](https://svend.ai).

**Live at [dugnadsand.org](https://dugnadsand.org).**

## What it is, and what it deliberately is not

It keeps records of what people gave — hours, and material — and none of them is a
currency. Nothing can be spent, nothing is owed by anyone to anyone, and **nothing in
the system gates on any of it**: you can receive having given nothing, ever.

The records are also kept apart. Hours and material sit in separate logs that are never
added together and never converted into one another, because an exchange rate between
timber and time would put a price on both. Material is described and counted; it is
never valued. See [design rules 9–11](docs/design-rules.md).

That last property is the whole design. It is what keeps this a gift rather than an
exchange, and it is what lets the organization keep offering help without eligibility
requirements. If you are reading this because you are about to add a feature, read
[docs/design-rules.md](docs/design-rules.md) first.

## Documentation

| | |
|---|---|
| [docs/board-case.md](docs/board-case.md) | The proposal a prospective organization's board would read |
| [docs/komunitin-comparison.md](docs/komunitin-comparison.md) | Why we did not adopt Komunitin, and what we kept from it |
| [docs/architecture.md](docs/architecture.md) | Code-level comparison with Komunitin: where the gate lives, and what replaces it |
| [docs/design-rules.md](docs/design-rules.md) | The eleven constraints that hold the model up |
| [docs/policy-manifest.md](docs/policy-manifest.md) | The claims that are enforced by code, and why INCOMPLETE is not a soft pass |
| [docs/how-it-works.md](docs/how-it-works.md) | What the system does, for somebody deciding whether to use it |
| [docs/warehouse.md](docs/warehouse.md) | The virtual warehouse and bills of material, and why neither carries a value |
| [docs/reuse.md](docs/reuse.md) | What was reused from the wider estate, and what could not be |

## License

**Code: [AGPL-3.0-only](LICENSE). Documentation: [CC BY 4.0](docs/LICENSE.md).**

Copyright © 2026 Eric Wolters.

The copyleft is doing a specific job here. This model rests on one claim — that nothing
in the system gates on what you have given — and we made that auditable in code rather
than promised in a policy. AGPL's network clause means anyone running a modified version
has to be able to show its source, so a member can always ask a community to prove the
claim still holds. A permissive license would allow a closed fork that quietly added
gating while keeping the name.

The docs are deliberately looser. If the reasoning in them helps another mutual aid
organization avoid building a barter exchange by accident, take it and go.

## Running it

Django 5, Postgres, gunicorn behind a Cloudflare tunnel. Configuration comes entirely
from the environment; nothing secret lives in this tree.

> `requirements.txt` lists `kjerne-platform`, a private package providing the shared mail
> queue and rate limiter. It is not publicly available, so a clone will not install
> cleanly as-is. Swap those two call sites in `site_app/views.py` for any mail backend
> and rate limiter you like — nothing else depends on it.

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Environment variables:

| Variable | Purpose |
|---|---|
| `DUGNADSAND_DATABASE_URL` | Postgres connection (`postgresql://…`) |
| `DUGNADSAND_SECRET_KEY` | Django secret key |
| `DUGNADSAND_ALLOWED_HOSTS` | Comma-separated hostnames |
| `DUGNADSAND_CONTACT_EMAIL` | Where the contact form delivers |
| `KJERNE_PLATFORM_DATABASE_URL` | Shared platform DB (mail queue, rate limiting) |

## Credits

Photographs are public domain, via Wikimedia Commons: *Community gathering at a barn
raising bee*, early 1900s, and *Little Bear Trail Work Day*, Coconino National Forest,
2016.

Nothing in this repository is legal advice. The tax and regulatory reasoning in the docs
reflects the questions the design was built around, and requires review by counsel.
