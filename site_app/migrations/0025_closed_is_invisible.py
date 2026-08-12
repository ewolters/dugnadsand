from django.db import migrations


class Migration(migrations.Migration):
    """A closed organization disappears from its chapter as well.

    0022 made the chapter the sharing boundary. Marking an organization
    inactive then stopped its own members signing in — but its postings,
    projects and material stayed visible to everyone else in the chapter,
    because the region clause matched on region_id and nothing else.

    Closed therefore meant closed to them and open to everybody, which is the
    opposite of what the word promises and exactly the sort of half-applied
    switch this flag already was.

    The organization keeps everything. Its rows remain readable inside its own
    tenant, which is what makes closing reversible.
    """


    dependencies = [("site_app", "0024_chapter_removal")]

    operations = [
        migrations.RunSQL(
            sql="""
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_claim;
            CREATE POLICY tenant_isolation_policy ON site_app_claim
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                                  AND active
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_clearance;
            CREATE POLICY tenant_isolation_policy ON site_app_clearance
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                                  AND active
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_comment;
            CREATE POLICY tenant_isolation_policy ON site_app_comment
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                                  AND active
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_contribution;
            CREATE POLICY tenant_isolation_policy ON site_app_contribution
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                                  AND active
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_interest;
            CREATE POLICY tenant_isolation_policy ON site_app_interest
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                                  AND active
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_manifest;
            CREATE POLICY tenant_isolation_policy ON site_app_manifest
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                                  AND active
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_materialgiven;
            CREATE POLICY tenant_isolation_policy ON site_app_materialgiven
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                                  AND active
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_materialneed;
            CREATE POLICY tenant_isolation_policy ON site_app_materialneed
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                                  AND active
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_measure;
            CREATE POLICY tenant_isolation_policy ON site_app_measure
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                                  AND active
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_member;
            CREATE POLICY tenant_isolation_policy ON site_app_member
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                                  AND active
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_packet;
            CREATE POLICY tenant_isolation_policy ON site_app_packet
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                                  AND active
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_photo;
            CREATE POLICY tenant_isolation_policy ON site_app_photo
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                                  AND active
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_photoconsent;
            CREATE POLICY tenant_isolation_policy ON site_app_photoconsent
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                                  AND active
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_pin;
            CREATE POLICY tenant_isolation_policy ON site_app_pin
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                                  AND active
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_posting;
            CREATE POLICY tenant_isolation_policy ON site_app_posting
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                                  AND active
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_project;
            CREATE POLICY tenant_isolation_policy ON site_app_project
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                                  AND active
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_stockline;
            CREATE POLICY tenant_isolation_policy ON site_app_stockline
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                                  AND active
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_warehouse;
            CREATE POLICY tenant_isolation_policy ON site_app_warehouse
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                                  AND active
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_workday;
            CREATE POLICY tenant_isolation_policy ON site_app_workday
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                                  AND active
                        )
                    )
                );
            """,
            reverse_sql="""
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_claim;
            CREATE POLICY tenant_isolation_policy ON site_app_claim
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_clearance;
            CREATE POLICY tenant_isolation_policy ON site_app_clearance
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_comment;
            CREATE POLICY tenant_isolation_policy ON site_app_comment
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_contribution;
            CREATE POLICY tenant_isolation_policy ON site_app_contribution
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_interest;
            CREATE POLICY tenant_isolation_policy ON site_app_interest
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_manifest;
            CREATE POLICY tenant_isolation_policy ON site_app_manifest
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_materialgiven;
            CREATE POLICY tenant_isolation_policy ON site_app_materialgiven
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_materialneed;
            CREATE POLICY tenant_isolation_policy ON site_app_materialneed
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_measure;
            CREATE POLICY tenant_isolation_policy ON site_app_measure
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_member;
            CREATE POLICY tenant_isolation_policy ON site_app_member
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_packet;
            CREATE POLICY tenant_isolation_policy ON site_app_packet
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_photo;
            CREATE POLICY tenant_isolation_policy ON site_app_photo
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_photoconsent;
            CREATE POLICY tenant_isolation_policy ON site_app_photoconsent
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_pin;
            CREATE POLICY tenant_isolation_policy ON site_app_pin
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_posting;
            CREATE POLICY tenant_isolation_policy ON site_app_posting
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_project;
            CREATE POLICY tenant_isolation_policy ON site_app_project
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_stockline;
            CREATE POLICY tenant_isolation_policy ON site_app_stockline
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_warehouse;
            CREATE POLICY tenant_isolation_policy ON site_app_warehouse
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                        )
                    )
                );
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_workday;
            CREATE POLICY tenant_isolation_policy ON site_app_workday
                USING (
                    organization_id::text = current_setting('app.current_tenant_id', TRUE)
                    OR (
                        NULLIF(current_setting('app.current_region_id', TRUE), '') IS NOT NULL
                        AND organization_id IN (
                            SELECT id FROM site_app_organization
                            WHERE region_id::text
                                  = current_setting('app.current_region_id', TRUE)
                        )
                    )
                );
            """,
        ),
    ]
