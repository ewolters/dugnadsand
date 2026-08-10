import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """A container for ongoing work, and the optional link from a posting.

    Row-level security is applied in the same migration that creates the table.
    A tenant-scoped table that exists for even one deploy without its policy is
    a table that has been readable across organizations, and there is no way to
    find out after the fact whether anyone looked.
    """

    dependencies = [("site_app", "0007_posting_needed_by")]

    operations = [
        migrations.CreateModel(
            name="Project",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=200)),
                ("description", models.TextField()),
                ("open", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("organization", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="projects", to="site_app.organization")),
                ("started_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="projects_started", to="site_app.member")),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddField(
            model_name="posting",
            name="project",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="postings", to="site_app.project"),
        ),
        migrations.RunSQL(
            # Copied clause for clause from 0003, including the setting NAME.
            # app.current_tenant_id, not app.current_tenant: current_setting on
            # an unset name returns NULL, organization_id::text = NULL is NULL,
            # and the policy would then admit nothing at all. It fails closed,
            # which is the right direction to fail, but it fails.
            sql="""
            ALTER TABLE site_app_project ENABLE ROW LEVEL SECURITY;
            ALTER TABLE site_app_project FORCE ROW LEVEL SECURITY;

            CREATE POLICY tenant_isolation_policy ON site_app_project
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));

            CREATE POLICY bypass_rls_policy ON site_app_project
                USING (current_setting('app.bypass_rls', TRUE) = 'on');
            """,
            reverse_sql="""
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_project;
            DROP POLICY IF EXISTS bypass_rls_policy ON site_app_project;
            ALTER TABLE site_app_project NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE site_app_project DISABLE ROW LEVEL SECURITY;
            """,
        ),
    ]
