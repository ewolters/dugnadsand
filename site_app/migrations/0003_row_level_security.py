"""Tenant isolation enforced by Postgres, not by application code.

Django connects as `dugnadsand_app`, which does not own these tables, so plain
ENABLE already binds it. FORCE is what also binds `dugnadsand_owner` — the role
that runs migrations — so no role is exempt by accident. Komunitin does the same
thing for the same reason.

The policy compares the row's organization to `app.current_tenant_id`. When that
setting is absent the comparison is NULL, no policy matches, and the table
returns nothing: **it fails closed**. A view that forgets its filter shows an
empty page rather than another organization's members.

`app.bypass_rls` is the single escape hatch, set only by
site_app.tenancy.bypass_rls() and used only by migrations. Keeping it to one
call site is what makes it auditable — an escape hatch used in twenty places is
not an escape hatch.

Organization itself is NOT protected: it is the tenant, not tenant-scoped, and
resolving which organization a request belongs to necessarily happens before a
tenant is in context. Attestation is not protected either — the manifest makes
claims about the codebase, which is identical for every organization, and the
public attestation page must be readable with no tenant bound at all.
"""

from django.db import migrations

TABLES = (
    "site_app_member",
    "site_app_offering",
    "site_app_claim",
    "site_app_contribution",
)

FORWARD = "\n".join(
    f"""
ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {t} FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_policy ON {t}
    USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));

CREATE POLICY bypass_rls_policy ON {t}
    USING (current_setting('app.bypass_rls', TRUE) = 'on');
"""
    for t in TABLES
)

REVERSE = "\n".join(
    f"""
DROP POLICY IF EXISTS tenant_isolation_policy ON {t};
DROP POLICY IF EXISTS bypass_rls_policy ON {t};
ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {t} DISABLE ROW LEVEL SECURITY;
"""
    for t in TABLES
)


class Migration(migrations.Migration):

    dependencies = [
        ("site_app", "0002_organization_member_offering_claim_contribution"),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE),
    ]
