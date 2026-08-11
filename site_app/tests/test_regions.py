"""Chapters, and the thing a chapter must never become.

The useful version of this feature is a roster: which organizations belong to
this chapter, and who runs it. The tempting version is a dashboard showing how
each of those organizations is doing, which is the same figure the ledger is
built not to compute, arriving at a level where nobody thought to forbid it.

So most of what is asserted here is absence. A chapter role reaches no tenant
data, and it reaches none by SHAPE rather than by a check somebody has to
remember to run.
"""

from django.contrib.auth.models import User
from django.test import TestCase

from site_app.models import (Member, Organization, Region, RegionRole,
                             TenantScoped)
from site_app.tenancy import set_tenant, tenant_context

from .helpers import SignedIn


class RegionBase(TestCase):
    def setUp(self):
        self.upstate = Region.objects.create(
            slug="upstate-sc", name="Upstate South Carolina",
            covers="Greenville, Pickens, Anderson and Spartanburg counties.")
        self.org = Organization.objects.create(
            slug="alpha", name="Alpha Mutual Aid", region=self.upstate)
        set_tenant(None)

    def tearDown(self):
        set_tenant(None)


class AChapterIsARosterNotALens(RegionBase):
    """The structural claim, asserted structurally.

    A chapter that could read across its organizations would falsify the
    sentence on /policy/ that every admitted organization is shown: that its
    members, postings, ledger, projects and material are invisible to every
    other organization. One chapter dashboard would break that for everybody
    in the chapter at once.
    """

    @staticmethod
    def tenant_models():
        from django.apps import apps

        return {m for m in apps.get_models() if issubclass(m, TenantScoped)}

    def test_no_chapter_table_points_at_tenant_data(self):
        tenant = self.tenant_models()
        for model in (Region, RegionRole):
            for field in model._meta.get_fields():
                related = getattr(field, "related_model", None)
                self.assertNotIn(
                    related, tenant,
                    f"{model.__name__}.{field.name} reaches {related and related.__name__}")

    def test_no_tenant_table_points_back_at_a_chapter(self):
        """The other direction, which is the one that would arrive quietly.

        A Region FK on Posting or Contribution would let a chapter be joined
        to member records without any chapter table changing at all.
        """
        for model in self.tenant_models():
            for field in model._meta.get_fields():
                related = getattr(field, "related_model", None)
                self.assertNotIn(
                    related, (Region, RegionRole),
                    f"{model.__name__}.{field.name} reaches a chapter")

    def test_the_only_link_is_a_label_on_the_tenant_root(self):
        links = [f.name for f in Organization._meta.get_fields()
                 if getattr(f, "related_model", None) in (Region, RegionRole)]
        self.assertEqual(links, ["region"])

    def test_a_chapter_can_list_its_organizations(self):
        """What a chapter IS for. Names and slugs, nothing inside them."""
        self.assertEqual([o.name for o in self.upstate.organizations.all()],
                         ["Alpha Mutual Aid"])


class AChapterRoleGrantsNoAccess(SignedIn, RegionBase):
    """The runtime half. Shape is the protection, but shape is a claim about
    code that has not been written yet, so this drives the real request path
    with a real chapter lead who is a member of nothing."""

    def setUp(self):
        super().setUp()
        self.lead_user = User.objects.create_user(
            "chapterlead", email="lead@example.test", password="dugnad-test-pw")
        RegionRole.objects.create(
            region=self.upstate, user=self.lead_user, role=RegionRole.LEAD,
            title="Convenor")

        self.member_user = User.objects.create_user(
            "ada", password="dugnad-test-pw")
        with tenant_context(self.org):
            self.member = Member.objects.create(
                organization=self.org, display_name="Ada", user=self.member_user)
        set_tenant(None)

    def test_the_lead_of_a_chapter_is_a_member_of_nothing(self):
        self.assertIsNone(getattr(self.lead_user, "member", None))

    def test_a_chapter_lead_cannot_reach_an_organizations_pages(self):
        self.sign_in(self.lead_user)
        for path in ("/board/", "/ledger/", "/projects/", "/warehouse/",
                     "/days/", "/members/"):
            response = self.client.get(path)
            self.assertNotEqual(
                response.status_code, 200,
                f"a chapter lead reached {path} with no membership")

    def test_a_member_of_that_organization_still_can(self):
        """Guard the guard: the refusal above must not be because every one of
        those pages is broken."""
        self.sign_in(self.member_user)
        for path in ("/board/", "/ledger/", "/days/"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_holding_a_role_does_not_create_a_membership(self):
        RegionRole.objects.create(
            region=self.upstate, user=self.lead_user, role=RegionRole.ADMIN)
        with tenant_context(self.org):
            self.assertEqual(
                Member.objects.filter(user=self.lead_user).count(), 0)


class ChapterRoles(RegionBase):
    def test_a_person_may_hold_one_role_of_each_kind(self):
        user = User.objects.create_user("pat", password="dugnad-test-pw")
        RegionRole.objects.create(region=self.upstate, user=user,
                                  role=RegionRole.LEAD)
        RegionRole.objects.create(region=self.upstate, user=user,
                                  role=RegionRole.ADMIN)
        self.assertEqual(RegionRole.objects.filter(user=user).count(), 2)

    def test_the_same_role_cannot_be_recorded_twice(self):
        from django.db import IntegrityError, transaction

        user = User.objects.create_user("pat", password="dugnad-test-pw")
        RegionRole.objects.create(region=self.upstate, user=user,
                                  role=RegionRole.LEAD)
        with self.assertRaises(IntegrityError), transaction.atomic():
            RegionRole.objects.create(region=self.upstate, user=user,
                                      role=RegionRole.LEAD)

    def test_a_chapter_may_be_named_locally(self):
        user = User.objects.create_user("pat", password="dugnad-test-pw")
        role = RegionRole.objects.create(
            region=self.upstate, user=user, role=RegionRole.ADMIN,
            title="Steward")
        self.assertEqual(role.title, "Steward")
        self.assertEqual(role.get_role_display(), "Administrator")


class OrganizationsWithoutAChapter(RegionBase):
    def test_an_organization_may_have_no_chapter(self):
        """SVEND was admitted before chapters existed, and a migration that
        forced every existing tenant into one would be inventing facts."""
        loose = Organization.objects.create(slug="beta", name="Beta")
        self.assertIsNone(loose.region)

    def test_a_chapter_cannot_be_deleted_out_from_under_its_organizations(self):
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            self.upstate.delete()
