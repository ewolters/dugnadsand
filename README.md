# Dugnadsand

*Dugnad* is the Norwegian word for work a neighborhood does together — the Saturday the
whole street turns out to clear the lot or paint the community hall, and nobody keeps
track of who owed what. *Dugnadsånd* is the spirit of it.

This is the site and, in time, the record-keeping for a mutual aid pilot in upstate
South Carolina, run under the 501(c)(3) of [Once Upon a Table, Inc.](https://southcarolinavoyager.com/interview/exploring-life-business-with-hannah-smith-of-once-upon-a-table-inc)
and sponsored by [SVEND](https://svend.ai).

**Live at [dugnadsand.org](https://dugnadsand.org).**

## What it is, and what it deliberately is not

It keeps one record: hours given. That record is not a currency. It cannot be spent, it
is not owed to anyone by anyone, and **nothing in the system gates on it** — you can
receive having given nothing, ever.

That last property is the whole design. It is what keeps this a gift rather than an
exchange, and it is what lets the organization keep offering help without eligibility
requirements. If you are reading this because you are about to add a feature, read
[docs/design-rules.md](docs/design-rules.md) first.

## Documentation

| | |
|---|---|
| [docs/board-case.md](docs/board-case.md) | The proposal to the Once Upon a Table board |
| [docs/komunitin-comparison.md](docs/komunitin-comparison.md) | Why we did not adopt Komunitin, and what we kept from it |
| [docs/design-rules.md](docs/design-rules.md) | The eight constraints that hold the model up |

## Running it

Django 5, Postgres, gunicorn behind a Cloudflare tunnel. Configuration comes entirely
from the environment; nothing secret lives in this tree.

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
