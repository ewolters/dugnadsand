"""Ongoing work, and the accountability it must never grow.

There is real project-management code in this federation and none of it could
be reused, which is worth stating precisely because "reuse the existing infra"
was the right instinct and the answer was still no.

  hoshined  hoshin/models/projects.py::Project — benefit_type (Operational /
            Capex Savings), gl_account, financial_category, assurance,
            needs_approval, approved_by, budgeted vs actual dates, owner.
  svend     hoshin/models.py::ActionItem — owner_name, status running to
            Completed and Blocked, due_date, progress, depends_on.

Both are good at their job: who owes what by when, and what was it worth. This
system is built so that question cannot be asked. The tests below are what stop
those fields arriving here one reasonable pull request at a time — because they
will be proposed, and each one on its own will sound like an improvement.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from site_app.models import Member, Organization, Posting, Project
from site_app.tenancy import bypass_rls, tenant_context

from .helpers import SignedIn


class ProjectBase(SignedIn, TestCase):
    def setUp(self):
        self.alpha = Organization.objects.create(slug="alpha", name="Alpha Mutual Aid")
        self.beta = Organization.objects.create(slug="beta", name="Beta Mutual Aid")

        self.ada_user = User.objects.create_user(
            "ada", email="ada@example.test", password="dugnad-test-pw")
        self.bo_user = User.objects.create_user(
            "bo", email="bo@example.test", password="dugnad-test-pw")

        with tenant_context(self.alpha):
            self.ada = Member.objects.create(
                organization=self.alpha, display_name="Ada", user=self.ada_user)
            self.homes = Project.objects.create(
                organization=self.alpha, started_by=self.ada,
                name="Repairing homes on the east side",
                description="Roofs, steps, ramps. Runs as long as it runs.")

        with tenant_context(self.beta):
            self.bo = Member.objects.create(
                organization=self.beta, display_name="Bo", user=self.bo_user)


class TheShapeItRefused(ProjectBase):
    """Field-level guards against the models this one did not copy."""

    def test_a_project_carries_no_owner_no_status_and_no_progress(self):
        """Assignment is obligation; a recorded completion is a duty owed."""
        fields = {f.name for f in Project._meta.get_fields()}
        for forbidden in ("owner", "owner_name", "assigned_to", "responsible",
                          "status", "progress", "percent_complete",
                          "due_date", "target_date", "deadline",
                          "depends_on", "blocked_by", "priority"):
            self.assertNotIn(forbidden, fields)

    def test_a_project_carries_no_valuation_of_any_kind(self):
        """flat-hours and no-tax-artifact. hoshined's Project exists to prove a
        saving; this one must not be able to express one."""
        fields = {f.name for f in Project._meta.get_fields()}
        for forbidden in ("benefit_type", "savings", "value", "budget", "cost",
                          "gl_account", "financial_category", "rate", "amount"):
            self.assertNotIn(forbidden, fields)

    def test_a_project_carries_no_approval_gate(self):
        """A gate is the thing this system removes. Nobody signs off on help."""
        fields = {f.name for f in Project._meta.get_fields()}
        for forbidden in ("needs_approval", "approved", "approved_by",
                          "approved_at", "sponsor", "authorised_by"):
            self.assertNotIn(forbidden, fields)

    def test_the_form_asks_for_a_name_and_a_description_and_nothing_else(self):
        from site_app.forms import ProjectForm

        self.assertEqual(set(ProjectForm().fields), {"name", "description"})


class NobodyIsInCharge(ProjectBase):
    def test_anyone_can_mark_a_project_finished_including_a_stranger_to_it(self):
        """There is no owner to ask. The absence has to be operable, not just
        absent from the schema — otherwise the first person to leave the
        organization strands whatever they wrote down."""
        outsider = User.objects.create_user(
            "kit", email="kit@example.test", password="dugnad-test-pw")
        with tenant_context(self.alpha):
            Member.objects.create(organization=self.alpha,
                                  display_name="Kit", user=outsider)

        self.sign_in(outsider)
        response = self.client.post(f"/projects/{self.homes.id}/close/")

        self.assertEqual(response.status_code, 302)
        with tenant_context(self.alpha):
            self.assertFalse(Project.objects.get(pk=self.homes.pk).open)

    def test_starting_a_project_records_who_wrote_it_down_not_who_owns_it(self):
        """started_by exists so a page can say where it came from. The test
        that keeps it honest is the one above: it confers nothing."""
        with tenant_context(self.alpha):
            self.assertEqual(self.homes.started_by, self.ada)


class ProjectsAreOptional(ProjectBase):
    def test_a_posting_belongs_to_no_project_by_default(self):
        with tenant_context(self.alpha):
            posting = Posting.objects.create(
                organization=self.alpha, member=self.ada, kind=Posting.NEED,
                description="A ride to the clinic.")
        self.assertIsNone(posting.project)

    def test_the_picker_offers_a_way_out_and_only_open_projects(self):
        from site_app.forms import PostingForm

        with tenant_context(self.alpha):
            Project.objects.create(
                organization=self.alpha, started_by=self.ada, open=False,
                name="Finished thing", description="Done.")
            form = PostingForm()
            names = {p.name for p in form.fields["project"].queryset}

        self.assertFalse(form.fields["project"].required)
        self.assertEqual(form.fields["project"].empty_label, "Not part of anything")
        self.assertNotIn("Finished thing", names)

    def test_filing_under_a_project_does_not_change_who_may_claim(self):
        """A project must not become a membership gate — the exact way a
        container quietly turns into an eligibility rule."""
        from site_app.services import claim_posting

        stranger_user = User.objects.create_user(
            "kit", email="kit@example.test", password="dugnad-test-pw")
        with tenant_context(self.alpha):
            stranger = Member.objects.create(
                organization=self.alpha, display_name="Kit", user=stranger_user)
            posting = Posting.objects.create(
                organization=self.alpha, member=self.ada, kind=Posting.NEED,
                project=self.homes, description="Hold a ladder.")
            # Kit has never touched this project and has given nothing.
            claim = claim_posting(posting=posting, member=stranger)

        self.assertEqual(claim.member, stranger)


class ProjectsAreTenantScoped(ProjectBase):
    def test_another_organization_cannot_see_a_project(self):
        with tenant_context(self.beta):
            self.assertEqual(Project.objects.count(), 0)

    def test_the_row_is_really_there_and_rls_is_what_hides_it(self):
        """Distinguishes 'isolated' from 'the migration silently failed'."""
        with bypass_rls():
            self.assertEqual(Project.objects.filter(pk=self.homes.pk).count(), 1)

    def test_a_project_page_is_not_reachable_from_another_organization(self):
        self.sign_in(self.bo_user)
        self.assertEqual(
            self.client.get(f"/projects/{self.homes.id}/").status_code, 404)


class NoTotalsAnywhere(ProjectBase):
    def test_the_project_page_shows_a_log_and_never_a_sum(self):
        """A project total describes work rather than a person, which is what
        makes it feel safe. With one contributor it IS that person's total."""
        from site_app.services import record_contribution

        with tenant_context(self.alpha):
            posting = Posting.objects.create(
                organization=self.alpha, member=self.ada, kind=Posting.OFFER,
                project=self.homes, description="Roofing.")
            for hours in ("3.00", "4.50"):
                record_contribution(posting=posting, member=self.ada,
                                    hours=Decimal(hours), note="")

        self.sign_in(self.ada_user)
        body = self.client.get(f"/projects/{self.homes.id}/").content.decode()

        # Both entries appear...
        self.assertIn("3.00", body)
        self.assertIn("4.50", body)
        # ...and their sum does not, in any of the ways it might be rendered.
        for total in ("7.50", "7.5", "7,50"):
            self.assertNotIn(total, body)

    def test_the_view_context_carries_no_aggregate_for_a_template_to_find(self):
        """Backstop for the test above: absent from the page is easy to
        reintroduce, absent from the context is not."""
        from site_app.services import record_contribution

        with tenant_context(self.alpha):
            posting = Posting.objects.create(
                organization=self.alpha, member=self.ada, kind=Posting.OFFER,
                project=self.homes, description="Roofing.")
            record_contribution(posting=posting, member=self.ada,
                                hours=Decimal("3.00"), note="")

        self.sign_in(self.ada_user)
        context = self.client.get(f"/projects/{self.homes.id}/").context

        for key in ("total", "total_hours", "hours_total", "sum", "aggregate"):
            self.assertNotIn(key, context)


class StartingOneTellsPeople(ProjectBase):
    def test_the_organization_hears_and_the_body_carries_no_project_name(self):
        """The name is the tempting exception and it is still refused:
        "Repairing homes on the east side" is as much somebody's circumstances
        as any posting description, and no test could tell the two apart."""
        from unittest.mock import patch

        with tenant_context(self.alpha):
            kit_user = User.objects.create_user(
                "kit", email="kit@example.test", password="dugnad-test-pw")
            Member.objects.create(organization=self.alpha,
                                  display_name="Kit", user=kit_user)

        self.sign_in(self.ada_user)
        with patch("kjerne_platform.notify.send") as send:
            self.client.post("/projects/new/", {
                "name": "Rebuilding the Henderson roof after the fire",
                "description": "Runs until it is done."})

        self.assertEqual({c.args[0] for c in send.call_args_list},
                         {"kit@example.test"})
        for call in send.call_args_list:
            self.assertNotIn("Henderson", call.args[3])
            self.assertNotIn("fire", call.args[3])

    def test_a_broken_notice_service_does_not_lose_the_project(self):
        from unittest.mock import patch

        self.sign_in(self.ada_user)
        with patch("kjerne_platform.notify.send", side_effect=RuntimeError("down")):
            response = self.client.post("/projects/new/", {
                "name": "Ramps", "description": "Building ramps."})

        self.assertEqual(response.status_code, 302)
        with tenant_context(self.alpha):
            self.assertTrue(Project.objects.filter(name="Ramps").exists())
