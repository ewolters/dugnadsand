import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """The virtual warehouse: Warehouse, StockLine, Manifest.

    Row-level security is applied in the same migration that creates the
    tables, and the clauses came out of kjerne_platform.work.scaffold rather
    than being retyped — the first real use of that generator, on the exact
    failure it was built for. 0008 was hand-typed against app.current_tenant
    where this estate uses app.current_tenant_id, and current_setting on an
    unset name returns NULL, so the policy admitted nothing.
    """

    dependencies = [("site_app", "0008_project")]

    operations = [
        migrations.CreateModel(
            name="Warehouse",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=200)),
                ("address", models.TextField()),
                ("notes", models.TextField(blank=True)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("organization", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="warehouses", to="site_app.organization")),
                ("holder", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="warehouses", to="site_app.member")),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="StockLine",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ("description", models.TextField()),
                ("quantity", models.DecimalField(decimal_places=2, max_digits=12)),
                ("unit", models.CharField(max_length=40)),
                ("confirmed_at", models.DateTimeField()),
                ("available", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("organization", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="stocklines", to="site_app.organization")),
                ("warehouse", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="lines", to="site_app.warehouse")),
                ("confirmed_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="stock_confirmations", to="site_app.member")),
            ],
            options={"ordering": ("-confirmed_at",)},
        ),
        migrations.CreateModel(
            name="Manifest",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ("quantity", models.DecimalField(decimal_places=2, max_digits=12)),
                ("destination", models.TextField()),
                ("sent_at", models.DateTimeField(auto_now_add=True)),
                ("received_at", models.DateTimeField(blank=True, null=True)),
                ("received_note", models.TextField(blank=True)),
                ("organization", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="manifests", to="site_app.organization")),
                ("stock_line", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="manifests", to="site_app.stockline")),
                ("sent_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="manifests_sent", to="site_app.member")),
            ],
            options={"ordering": ("-sent_at",)},
        ),
        migrations.RunSQL(
            sql="""
            ALTER TABLE site_app_warehouse ENABLE ROW LEVEL SECURITY;
            ALTER TABLE site_app_warehouse FORCE ROW LEVEL SECURITY;

            CREATE POLICY tenant_isolation_policy ON site_app_warehouse
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));

            CREATE POLICY bypass_rls_policy ON site_app_warehouse
                USING (current_setting('app.bypass_rls', TRUE) = 'on');
            ALTER TABLE site_app_stockline ENABLE ROW LEVEL SECURITY;
            ALTER TABLE site_app_stockline FORCE ROW LEVEL SECURITY;

            CREATE POLICY tenant_isolation_policy ON site_app_stockline
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));

            CREATE POLICY bypass_rls_policy ON site_app_stockline
                USING (current_setting('app.bypass_rls', TRUE) = 'on');
            ALTER TABLE site_app_manifest ENABLE ROW LEVEL SECURITY;
            ALTER TABLE site_app_manifest FORCE ROW LEVEL SECURITY;

            CREATE POLICY tenant_isolation_policy ON site_app_manifest
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));

            CREATE POLICY bypass_rls_policy ON site_app_manifest
                USING (current_setting('app.bypass_rls', TRUE) = 'on');
            """,
            reverse_sql="""
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_warehouse;
            DROP POLICY IF EXISTS bypass_rls_policy ON site_app_warehouse;
            ALTER TABLE site_app_warehouse NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE site_app_warehouse DISABLE ROW LEVEL SECURITY;
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_stockline;
            DROP POLICY IF EXISTS bypass_rls_policy ON site_app_stockline;
            ALTER TABLE site_app_stockline NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE site_app_stockline DISABLE ROW LEVEL SECURITY;
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_manifest;
            DROP POLICY IF EXISTS bypass_rls_policy ON site_app_manifest;
            ALTER TABLE site_app_manifest NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE site_app_manifest DISABLE ROW LEVEL SECURITY;
            """,
        ),
    ]
