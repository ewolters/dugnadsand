from django.db import migrations


class Migration(migrations.Migration):
    """The chapter is the sharing boundary, not the organization.

    A mutual aid network is MANY organizations -- most of them one or two
    people -- and the whole point is that they can see each other's offers and
    needs. Keying visibility on the organization meant two neighbours in one
    chapter were as invisible to each other as two strangers in different
    states, which is the network not existing.

    Every policy now admits a row when EITHER

        it belongs to my organization                (unchanged), or
        it belongs to an organization in MY CHAPTER  (new).

    What does NOT change:

      Writes. A new row still carries the writing member's own
      organization_id, so a posting Hannah writes stays Hannah's.

      Chapter-to-chapter isolation. Upstate/WNC cannot see Midlands: the
      clause matches on region_id equality, so another chapter matches
      nothing.

      Failing closed. NULLIF(..., '') IS NOT NULL is load-bearing. With no
      chapter bound, or an organization admitted into no chapter, the clause
      is false rather than NULL-and-forgotten, and the row stays scoped to
      the organization exactly as before -- so two chapterless organizations
      remain invisible to each other.

    bypass_rls_policy is untouched and remains the only escape hatch.
    """

    dependencies = [("site_app", "0021_photo_consent")]

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
            reverse_sql="""
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_claim;
            CREATE POLICY tenant_isolation_policy ON site_app_claim
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_clearance;
            CREATE POLICY tenant_isolation_policy ON site_app_clearance
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_comment;
            CREATE POLICY tenant_isolation_policy ON site_app_comment
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_contribution;
            CREATE POLICY tenant_isolation_policy ON site_app_contribution
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_manifest;
            CREATE POLICY tenant_isolation_policy ON site_app_manifest
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_materialgiven;
            CREATE POLICY tenant_isolation_policy ON site_app_materialgiven
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_materialneed;
            CREATE POLICY tenant_isolation_policy ON site_app_materialneed
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_measure;
            CREATE POLICY tenant_isolation_policy ON site_app_measure
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_member;
            CREATE POLICY tenant_isolation_policy ON site_app_member
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_packet;
            CREATE POLICY tenant_isolation_policy ON site_app_packet
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_photo;
            CREATE POLICY tenant_isolation_policy ON site_app_photo
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_photoconsent;
            CREATE POLICY tenant_isolation_policy ON site_app_photoconsent
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_pin;
            CREATE POLICY tenant_isolation_policy ON site_app_pin
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_posting;
            CREATE POLICY tenant_isolation_policy ON site_app_posting
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_project;
            CREATE POLICY tenant_isolation_policy ON site_app_project
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_stockline;
            CREATE POLICY tenant_isolation_policy ON site_app_stockline
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_warehouse;
            CREATE POLICY tenant_isolation_policy ON site_app_warehouse
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));
            DROP POLICY IF EXISTS tenant_isolation_policy ON site_app_workday;
            CREATE POLICY tenant_isolation_policy ON site_app_workday
                USING (organization_id::text = current_setting('app.current_tenant_id', TRUE));
            """,
        ),
    ]
