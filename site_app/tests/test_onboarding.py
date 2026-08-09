"""Admission: how an organization and its members come to exist.

There is no sign-up form and no Django admin. An organization is admitted by
somebody who decided to admit it, and a member is added by somebody who is
already talking to them. These tests hold that shape in place.
"""

from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .helpers import SignedIn
from django.urls import NoReverseMatch, reverse

from site_app.models import Member, Organization
from site_app.tenancy import bypass_rls, set_tenant, tenant_context


class AdmitOrganization(SignedIn, TestCase):
    def tearDown(self):
        set_tenant(None)

    def test_it_admits_an_organization_and_derives_a_slug(self):
        out = StringIO()
        call_command("admit_organization", "Rivertown Mutual Aid", stdout=out)

        org = Organization.objects.get(slug="rivertown-mutual-aid")
        self.assertEqual(org.name, "Rivertown Mutual Aid")
        self.assertTrue(org.active)
        self.assertIn("Admitted", out.getvalue())

    def test_an_explicit_slug_wins(self):
        call_command("admit_organization", "Rivertown Mutual Aid", slug="rma",
                     stdout=StringIO())
        self.assertTrue(Organization.objects.filter(slug="rma").exists())

    def test_admitting_the_same_organization_twice_is_refused(self):
        call_command("admit_organization", "Alpha", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("admit_organization", "Alpha", stdout=StringIO())
        self.assertEqual(Organization.objects.filter(slug="alpha").count(), 1)


class AddMember(SignedIn, TestCase):
    def setUp(self):
        call_command("admit_organization", "Alpha Mutual Aid", slug="alpha",
                     stdout=StringIO())
        self.org = Organization.objects.get(slug="alpha")

    def tearDown(self):
        set_tenant(None)

    def test_it_creates_a_login_and_a_membership(self):
        out = StringIO()
        call_command("add_member", "alpha", "ada", "Ada", "ada@example.org", stdout=out)

        user = User.objects.get(username="ada")
        with tenant_context(self.org):
            member = Member.objects.get(user=user)
            self.assertEqual(member.display_name, "Ada")
            self.assertEqual(member.organization_id, self.org.id)
        self.assertIn("password:", out.getvalue())

    def test_the_printed_password_works_and_lands_on_the_second_factor(self):
        """A handed-over password signs in, and stops at the second factor.

        Two gates stand in front of a brand-new member, in this order: set up a
        second factor, then replace the password somebody typed for you. MFA
        comes first because the password page changes a credential and should
        itself sit behind a full sign-in.
        """
        out = StringIO()
        call_command("add_member", "alpha", "ada", "Ada", "ada@example.org", stdout=out)
        password = [ln.split("password:")[1].strip()
                    for ln in out.getvalue().splitlines() if "password:" in ln][0]

        set_tenant(None)
        response = self.client.post(
            "/login/", {"username": "ada", "password": password}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain[-1][0], "/mfa/setup/")

    def test_an_unknown_organization_is_refused(self):
        with self.assertRaises(CommandError):
            call_command("add_member", "nope", "ada", "Ada", "ada@example.org", stdout=StringIO())
        self.assertFalse(User.objects.filter(username="ada").exists())

    def test_a_duplicate_username_is_refused_without_leaving_a_stray_user(self):
        call_command("add_member", "alpha", "ada", "Ada", "ada@example.org", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("add_member", "alpha", "ada", "Ada Again", "ada@example.org", stdout=StringIO())
        self.assertEqual(User.objects.filter(username="ada").count(), 1)
        with bypass_rls():
            self.assertEqual(Member.objects.filter(display_name="Ada Again").count(), 0)

    def test_two_organizations_can_hold_members_of_the_same_name(self):
        call_command("admit_organization", "Beta", stdout=StringIO())
        call_command("add_member", "alpha", "ada", "Ada", "ada@example.org", stdout=StringIO())
        call_command("add_member", "beta", "ada2", "Ada", "ada2@example.org", stdout=StringIO())
        with bypass_rls():
            self.assertEqual(Member.objects.filter(display_name="Ada").count(), 2)


class NoAdminSurface(SignedIn, TestCase):
    """Django admin is not mounted, and must not drift back.

    It arrived from the create-site scaffold with nothing registered, making it
    pure attack surface, and dugnadsand was the only site in the fleet exposing
    it. Members sign in through the in-app login.
    """

    def test_the_admin_url_is_not_routable(self):
        with self.assertRaises(NoReverseMatch):
            reverse("admin:index")

    def test_the_admin_path_is_not_served(self):
        self.assertEqual(self.client.get("/admin/").status_code, 404)

    def test_there_is_no_signup_page(self):
        # Admission is a conversation, not a button - the login page says so.
        for path in ("/signup/", "/register/", "/join/"):
            self.assertEqual(self.client.get(path).status_code, 404, path)
