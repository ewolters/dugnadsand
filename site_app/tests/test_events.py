"""Work days, and the one gate this system allows.

Everything else here refuses to withhold. This withholds -- a work day stays
unannounced until somebody records that the county, the landowner or the
insurer said yes. The tests that matter most are therefore not the ones
proving the gate works, but the ones proving it is the gate we think it is:
that it reads the clearance table and cannot read a member, and that it never
grew a second input.
"""

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from site_app.models import (Clearance, Contribution, Member, Organization,
                             WorkDay)
from site_app.services_events import (NotCleared, call_work_day, cancel,
                                      publish, record_clearance,
                                      require_clearance)
from site_app.tenancy import set_tenant, tenant_context

from .helpers import SignedIn


class WorkDayBase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(slug="alpha", name="Alpha Mutual Aid")
        self.user = User.objects.create_user("ada", password="dugnad-test-pw")
        with tenant_context(self.org):
            self.member = Member.objects.create(
                organization=self.org, display_name="Ada", user=self.user)
        set_tenant(None)

    def tearDown(self):
        set_tenant(None)

    def a_work_day(self, **kw):
        return call_work_day(
            organization=self.org, member=self.member,
            name="Reedy River cleanup",
            description="Waders, gloves and a skip.",
            starts_at=timezone.now() + timedelta(days=10),
            place="The Cedar Lane put-in, park on the grass by the gate.",
            **kw)


class TheClearanceGate(WorkDayBase):
    def test_a_day_with_nothing_required_publishes(self):
        """The gate is not a ceremony. Nothing outstanding means nothing to
        wait for, and a roadside litter pick needs nobody's permission."""
        with tenant_context(self.org):
            day = self.a_work_day()
            self.assertTrue(day.clear)
            publish(day)
            self.assertTrue(day.published)

    def test_an_outstanding_clearance_refuses_publication(self):
        with tenant_context(self.org):
            day = self.a_work_day()
            require_clearance(
                work_day=day, member=self.member, kind="River access permit",
                authority="Greenville County Parks")

            with self.assertRaises(NotCleared) as caught:
                publish(day)

            self.assertIn("River access permit", str(caught.exception))
            day.refresh_from_db()
            self.assertIsNone(day.published_at)

    def test_obtaining_it_releases_the_day(self):
        with tenant_context(self.org):
            day = self.a_work_day()
            clearance = require_clearance(
                work_day=day, member=self.member, kind="River access permit",
                authority="Greenville County Parks")
            record_clearance(
                clearance=clearance,
                obtained_on=date.today(), reference="PR-2026-1184")

            publish(day)
            self.assertTrue(WorkDay.objects.get(pk=day.pk).published)

    def test_a_lapsed_clearance_blocks_again(self):
        """A permit for last Sunday is not a permit.

        This is the failure nobody notices: the row is filled in, the page
        looks green, and the date on it is three weeks old.
        """
        with tenant_context(self.org):
            day = self.a_work_day()
            clearance = require_clearance(
                work_day=day, member=self.member, kind="Event permit",
                authority="City of Greenville")
            record_clearance(
                clearance=clearance,
                obtained_on=date.today() - timedelta(days=30),
                expires_on=date.today() - timedelta(days=1))

            self.assertFalse(WorkDay.objects.get(pk=day.pk).clear)
            with self.assertRaises(NotCleared):
                publish(day)

    def test_a_clearance_with_no_expiry_does_not_lapse(self):
        """"The owner said yes" does not expire, and treating it as though it
        did would make the gate cry wolf until people routed around it."""
        with tenant_context(self.org):
            day = self.a_work_day()
            clearance = require_clearance(
                work_day=day, member=self.member, kind="Landowner permission",
                authority="Mrs Alderman, the farm at the bend")
            record_clearance(
                clearance=clearance,
                obtained_on=date.today() - timedelta(days=400))

            self.assertTrue(WorkDay.objects.get(pk=day.pk).clear)

    def test_publishing_twice_does_not_move_the_timestamp(self):
        with tenant_context(self.org):
            day = publish(self.a_work_day())
            first = day.published_at
            publish(day)
            self.assertEqual(WorkDay.objects.get(pk=day.pk).published_at, first)

    def test_every_blocker_is_named_not_just_the_first(self):
        """Somebody chasing permissions needs the whole list, or they make
        three phone calls on three separate days."""
        with tenant_context(self.org):
            day = self.a_work_day()
            for kind, who in (("Event permit", "City of Greenville"),
                              ("River access", "County Parks"),
                              ("Certificate of insurance", "Our carrier")):
                require_clearance(work_day=day, member=self.member,
                                  kind=kind, authority=who)

            with self.assertRaises(NotCleared) as caught:
                publish(day)

            self.assertEqual(len(caught.exception.blockers), 3)
            for kind in ("Event permit", "River access",
                         "Certificate of insurance"):
                self.assertIn(kind, str(caught.exception))


class TheGateIsNotAMemberGate(WorkDayBase):
    """The claim that makes this feature admissible at all.

    no-gating forbids the record of what a member has given from deciding what
    that member may receive. This gate decides whether a DAY may be announced,
    on the say-so of a county. Those are different things, but they are one
    careless join apart -- "only publish if enough people have signed up"
    would be the whole design undone by a feature request.

    So the distinction is asserted rather than asserted-in-a-comment.
    """

    def test_publishing_never_reads_a_member_or_a_contribution(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with tenant_context(self.org):
            day = self.a_work_day()

            with CaptureQueriesContext(connection) as ctx:
                publish(day)

            # Guard the guard: prove the publish path actually ran.
            self.assertTrue(WorkDay.objects.get(pk=day.pk).published)

            touched = " ".join(q["sql"].lower() for q in ctx.captured_queries)
            self.assertIn("site_app_clearance", touched,
                          "the gate did not consult the clearance table")
            for forbidden in ("site_app_contribution", "site_app_claim",
                              "site_app_member"):
                self.assertNotIn(forbidden, touched,
                                 f"the publication gate read {forbidden}")

    def test_a_day_publishes_for_a_member_who_has_given_nothing(self):
        with tenant_context(self.org):
            self.assertEqual(
                Contribution.objects.filter(member=self.member).count(), 0)
            publish(self.a_work_day())

    def test_the_model_carries_no_attendance_or_headcount_field(self):
        """Obligation arrives through the door marked "who is coming".

        An expected-attendees field becomes a shortfall, a shortfall becomes a
        chase, and a chase is a duty owed -- which no-obligation forbids. The
        field names are asserted rather than the behaviour because the field
        is the thing that cannot exist.
        """
        names = {f.name for f in WorkDay._meta.get_fields()}
        for forbidden in ("attendees", "attending", "headcount", "capacity",
                          "expected", "signups", "rsvp", "quota", "target",
                          "minimum_volunteers", "confirmed_by"):
            self.assertNotIn(forbidden, names, f"WorkDay grew {forbidden}")


class ClearanceIsEvidenceNotPermission(WorkDayBase):
    def test_an_outstanding_requirement_exists_as_a_row(self):
        """Modelled on MaterialNeed: the requirement is visible before it is
        met, rather than being an absence nobody notices."""
        with tenant_context(self.org):
            day = self.a_work_day()
            require_clearance(work_day=day, member=self.member,
                              kind="Event permit", authority="The city")

            fresh = WorkDay.objects.get(pk=day.pk)
            self.assertEqual(len(fresh.outstanding), 1)
            self.assertFalse(fresh.outstanding[0].obtained)

    def test_it_keeps_a_reference_somebody_else_can_check(self):
        with tenant_context(self.org):
            day = self.a_work_day()
            clearance = require_clearance(
                work_day=day, member=self.member, kind="Event permit",
                authority="City of Greenville")
            record_clearance(clearance=clearance,
                             obtained_on=date.today(), reference="EV-9912")

            self.assertEqual(
                Clearance.objects.get(pk=clearance.pk).reference, "EV-9912")

    def test_it_records_no_value_and_no_hours(self):
        """A clearance is paperwork. The moment it carries a cost it is a
        purchase, and this system prices nothing."""
        names = {f.name for f in Clearance._meta.get_fields()}
        for forbidden in ("cost", "fee", "price", "value", "amount", "hours"):
            self.assertNotIn(forbidden, names, f"Clearance grew {forbidden}")


class CancellingIsATimestamp(WorkDayBase):
    def test_a_cancelled_day_is_no_longer_published(self):
        with tenant_context(self.org):
            day = publish(self.a_work_day())
            cancel(day, because="The river came up overnight.")

            fresh = WorkDay.objects.get(pk=day.pk)
            self.assertFalse(fresh.published)
            self.assertIn("river came up", fresh.cancelled_because)

    def test_the_model_carries_no_status_workflow(self):
        names = {f.name for f in WorkDay._meta.get_fields()}
        for forbidden in ("status", "state", "stage", "progress", "approved"):
            self.assertNotIn(forbidden, names, f"WorkDay grew {forbidden}")


class WorkDaysAreTenantScoped(SignedIn, TestCase):
    """Every other table is isolated by row-level security. A new one that is
    not would be a hole in the only boundary this system has."""

    def setUp(self):
        self.alpha = Organization.objects.create(slug="alpha", name="Alpha")
        self.beta = Organization.objects.create(slug="beta", name="Beta")
        self.alpha_user = User.objects.create_user("ada", password="dugnad-test-pw")
        with tenant_context(self.alpha):
            self.ada = Member.objects.create(
                organization=self.alpha, display_name="Ada", user=self.alpha_user)
            self.alpha_day = call_work_day(
                organization=self.alpha, member=self.ada, name="Alpha cleanup",
                description="Ours.", starts_at=timezone.now() + timedelta(days=3),
                place="Alpha's river.")
        set_tenant(None)

    def tearDown(self):
        set_tenant(None)

    def test_another_organization_cannot_see_the_day(self):
        with tenant_context(self.beta):
            self.assertEqual(WorkDay.objects.count(), 0)

    def test_the_owning_organization_can(self):
        with tenant_context(self.alpha):
            self.assertEqual(WorkDay.objects.count(), 1)

    def test_clearances_are_isolated_too(self):
        with tenant_context(self.alpha):
            require_clearance(work_day=self.alpha_day, member=self.ada,
                              kind="Permit", authority="The city")
        with tenant_context(self.beta):
            self.assertEqual(Clearance.objects.count(), 0)


class TheWorkDayPages(SignedIn, WorkDayBase):
    """The screens. The one that matters is announcing, because that is the
    only button in this system that can refuse."""

    def setUp(self):
        super().setUp()
        self.sign_in(self.user)

    def test_the_list_is_reachable_and_separates_announced_from_waiting(self):
        with tenant_context(self.org):
            waiting = self.a_work_day()
            require_clearance(work_day=waiting, member=self.member,
                              kind="Event permit", authority="The city")
            publish(self.a_work_day())

        body = self.client.get("/days/").content.decode()
        self.assertEqual(self.client.get("/days/").status_code, 200)
        self.assertIn("Announced", body)
        self.assertIn("Waiting on permission", body)
        self.assertIn("Event permit", body)

    def test_putting_a_day_in_creates_it_unannounced(self):
        starts = (timezone.now() + timedelta(days=14)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post("/days/new/", {
            "name": "Reedy River cleanup", "description": "Waders and gloves.",
            "project": "", "starts_at": starts, "ends_at": "",
            "place": "Cedar Lane put-in.", "muster": ""})
        self.assertEqual(response.status_code, 302)

        with tenant_context(self.org):
            day = WorkDay.objects.get(name="Reedy River cleanup")
            self.assertIsNone(day.published_at)

    def test_announcing_is_refused_and_says_what_is_missing(self):
        """The refusal has to reach the page. messages are rendered by
        board.html and nowhere else, so a message raised here would have been
        swallowed and the button would look broken rather than blocked."""
        with tenant_context(self.org):
            day = self.a_work_day()
            require_clearance(work_day=day, member=self.member,
                              kind="River access permit",
                              authority="Greenville County Parks")

        response = self.client.post(f"/days/{day.id}/announce/", follow=True)
        body = response.content.decode()
        self.assertIn("River access permit", body)
        self.assertIn("Greenville County Parks", body)

        with tenant_context(self.org):
            self.assertIsNone(WorkDay.objects.get(pk=day.pk).published_at)

    def test_recording_the_clearance_then_announcing_works(self):
        with tenant_context(self.org):
            day = self.a_work_day()
            clearance = require_clearance(
                work_day=day, member=self.member, kind="River access permit",
                authority="Greenville County Parks")

        self.client.post(f"/days/clearance/{clearance.id}/", {
            "obtained_on": date.today().isoformat(), "reference": "PR-2026-1184",
            "expires_on": "", "note": "Spoke to Dana at Parks."})
        self.client.post(f"/days/{day.id}/announce/")

        with tenant_context(self.org):
            fresh = WorkDay.objects.get(pk=day.pk)
            self.assertTrue(fresh.published)
            self.assertEqual(
                Clearance.objects.get(pk=clearance.pk).reference, "PR-2026-1184")

    def test_the_announce_button_is_disabled_while_blocked(self):
        """Disabled as well as refused. Offering a button that cannot work is
        how somebody concludes the page is broken."""
        with tenant_context(self.org):
            day = self.a_work_day()
            require_clearance(work_day=day, member=self.member,
                              kind="Event permit", authority="The city")

        body = self.client.get(f"/days/{day.id}/").content.decode()
        self.assertIn("disabled", body)

    def test_a_cleared_day_offers_a_live_button(self):
        with tenant_context(self.org):
            day = self.a_work_day()
        body = self.client.get(f"/days/{day.id}/").content.decode()
        self.assertIn("Announce it", body)
        self.assertNotIn("disabled", body)

    def test_the_page_says_recording_a_permission_does_not_create_one(self):
        """The disclaimer travels with the artifact, as it does on the
        attestation and the manifest."""
        import re

        with tenant_context(self.org):
            day = self.a_work_day()
        body = re.sub(r"\s+", " ", self.client.get(f"/days/{day.id}/").content.decode())
        self.assertIn("does not create it", body)

    def test_adding_a_requirement_from_the_page(self):
        with tenant_context(self.org):
            day = self.a_work_day()

        self.client.post(f"/days/{day.id}/", {
            "kind": "Certificate of insurance", "authority": "Our carrier",
            "note": ""})

        with tenant_context(self.org):
            self.assertEqual(
                Clearance.objects.filter(work_day=day).count(), 1)

    def test_calling_it_off_records_the_reason(self):
        with tenant_context(self.org):
            day = publish(self.a_work_day())

        self.client.post(f"/days/{day.id}/off/",
                         {"because": "The river came up overnight."})

        with tenant_context(self.org):
            fresh = WorkDay.objects.get(pk=day.pk)
            self.assertFalse(fresh.published)
            self.assertIn("river came up", fresh.cancelled_because)

    def test_a_day_from_another_organization_is_not_reachable(self):
        other = Organization.objects.create(slug="beta", name="Beta")
        other_user = User.objects.create_user("ola", password="dugnad-test-pw")
        with tenant_context(other):
            ola = Member.objects.create(
                organization=other, display_name="Ola", user=other_user)
            theirs = call_work_day(
                organization=other, member=ola, name="Theirs",
                description="Not ours.",
                starts_at=timezone.now() + timedelta(days=2), place="Elsewhere.")
        set_tenant(None)

        self.assertEqual(self.client.get(f"/days/{theirs.id}/").status_code, 404)
