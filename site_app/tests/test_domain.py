"""Domain and tenancy tests.

The tenancy ones matter most. A migration that ran is not the same as isolation
that works, so these bind a connection to one organization and assert the other
organization's rows are genuinely unreachable — not filtered out by a queryset
we could forget to write, but absent.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from .helpers import SignedIn

from site_app import services
from site_app.models import Claim, Contribution, Member, Offering, Organization
from site_app.tenancy import bypass_rls, set_tenant, tenant_context


class TenancyBase(SignedIn, TestCase):
    def setUp(self):
        # Organization is not tenant-scoped, so it is writable with no tenant bound.
        self.alpha = Organization.objects.create(slug="alpha", name="Alpha Mutual Aid")
        self.beta = Organization.objects.create(slug="beta", name="Beta Mutual Aid")

        with tenant_context(self.alpha):
            self.a_member = Member.objects.create(
                organization=self.alpha, display_name="Ada")
            self.a_offering = Offering.objects.create(
                organization=self.alpha, member=self.a_member,
                description="Two crates of potatoes, dug this morning.")

        with tenant_context(self.beta):
            self.b_member = Member.objects.create(
                organization=self.beta, display_name="Bo")
            self.b_offering = Offering.objects.create(
                organization=self.beta, member=self.b_member,
                description="Ladder, free to borrow.")

    def tearDown(self):
        set_tenant(None)


class TenantIsolation(TenancyBase):
    def test_one_organization_cannot_see_another(self):
        with tenant_context(self.alpha):
            names = list(Member.objects.values_list("display_name", flat=True))
        self.assertEqual(names, ["Ada"], "Beta's members were visible inside Alpha")

        with tenant_context(self.beta):
            names = list(Member.objects.values_list("display_name", flat=True))
        self.assertEqual(names, ["Bo"], "Alpha's members were visible inside Beta")

    def test_it_fails_closed_with_no_tenant_bound(self):
        # The property that matters: forgetting the filter shows nothing, rather
        # than showing everything.
        set_tenant(None)
        self.assertEqual(Member.objects.count(), 0)
        self.assertEqual(Offering.objects.count(), 0)
        self.assertEqual(Claim.objects.count(), 0)
        self.assertEqual(Contribution.objects.count(), 0)

    def test_a_row_from_another_tenant_is_not_reachable_by_id(self):
        # Not merely absent from a list — unreachable when its exact id is known.
        with tenant_context(self.alpha):
            self.assertFalse(Offering.objects.filter(pk=self.b_offering.pk).exists())

    def test_bypass_is_the_only_way_to_see_across_tenants(self):
        set_tenant(None)
        with bypass_rls():
            self.assertEqual(Member.objects.count(), 2)


class Claiming(TenancyBase):
    def test_a_member_who_has_given_nothing_may_still_claim(self):
        """The entire point of the system, as a test."""
        with tenant_context(self.alpha):
            self.assertEqual(Contribution.objects.filter(member=self.a_member).count(), 0)
            claim = services.claim_offering(offering=self.a_offering, member=self.a_member)
            self.assertIsNotNone(claim.pk)

    def test_claiming_across_organizations_is_refused(self):
        with tenant_context(self.alpha):
            with bypass_rls():
                with self.assertRaises(ValueError):
                    services.claim_offering(
                        offering=self.b_offering, member=self.a_member)

    def test_a_closed_offering_cannot_be_claimed(self):
        with tenant_context(self.alpha):
            self.a_offering.open = False
            self.a_offering.save()
            with self.assertRaises(ValueError):
                services.claim_offering(offering=self.a_offering, member=self.a_member)


class Contributions(TenancyBase):
    def test_hours_are_recorded_and_chain(self):
        with tenant_context(self.alpha):
            first = services.record_contribution(
                member=self.a_member, offering=self.a_offering, hours=Decimal("3.5"))
            second = services.record_contribution(
                member=self.a_member, offering=self.a_offering, hours=Decimal("1.0"))

            self.assertEqual(first.sequence, 0)
            self.assertEqual(second.sequence, 1)
            self.assertEqual(second.previous_hash, first.entry_hash)

            report = services.verify_contributions(self.alpha)
            self.assertTrue(report.ok, getattr(report, "problems", report))

    def test_rewriting_a_contribution_breaks_the_chain(self):
        with tenant_context(self.alpha):
            services.record_contribution(
                member=self.a_member, offering=self.a_offering, hours=Decimal("2"))
            services.record_contribution(
                member=self.a_member, offering=self.a_offering, hours=Decimal("2"))

            first = Contribution.objects.order_by("sequence").first()
            Contribution.objects.filter(pk=first.pk).update(hours=Decimal("40"))

            report = services.verify_contributions(self.alpha)
            self.assertFalse(report.ok, "an inflated contribution verified clean")

    def test_each_organization_chains_independently(self):
        with tenant_context(self.alpha):
            services.record_contribution(
                member=self.a_member, offering=self.a_offering, hours=Decimal("1"))
        with tenant_context(self.beta):
            b = services.record_contribution(
                member=self.b_member, offering=self.b_offering, hours=Decimal("1"))
            # Beta's chain starts at zero regardless of what Alpha has recorded.
            self.assertEqual(b.sequence, 0)
            self.assertEqual(b.previous_hash, "")

    def test_zero_or_negative_hours_are_refused(self):
        with tenant_context(self.alpha):
            for bad in (Decimal("0"), Decimal("-1")):
                with self.assertRaises(ValueError):
                    services.record_contribution(
                        member=self.a_member, offering=self.a_offering, hours=bad)


class ClaimEndpoint(TenancyBase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user("ada", password="dugnad-test-pw")
        with tenant_context(self.alpha):
            self.a_member.user = self.user
            self.a_member.save()

    def test_posting_a_claim_creates_one(self):
        self.sign_in(self.user)
        response = self.client.post(f"/offerings/{self.a_offering.id}/claim/")
        self.assertEqual(response.status_code, 302)

        with tenant_context(self.alpha):
            self.assertEqual(Claim.objects.filter(offering=self.a_offering).count(), 1)

    def test_anonymous_cannot_claim(self):
        response = self.client.post(f"/offerings/{self.a_offering.id}/claim/")
        self.assertIn(response.status_code, (302, 403))
        with tenant_context(self.alpha):
            self.assertEqual(Claim.objects.count(), 0)
