"""Passwords and organizers.

Two properties matter here. A handed-over password must stop working as a
handed-over password — the member is made to replace it before they can do
anything. And an organizer's privilege is exactly one thing: adding people. It
buys no extra view of the ledger, because there is no view to buy.
"""

import re

from django.contrib.auth.models import User
from django.test import TestCase

from .helpers import SignedIn

from site_app.models import Member, Posting, Organization
from site_app.services_members import MemberExists, create_member
from site_app.tenancy import bypass_rls, set_tenant, tenant_context


class MembersBase(SignedIn, TestCase):
    def setUp(self):
        self.alpha = Organization.objects.create(slug="alpha", name="Alpha Mutual Aid")
        self.beta = Organization.objects.create(slug="beta", name="Beta Mutual Aid")

        self.organizer, self.organizer_pw = create_member(
            organization=self.alpha, username="ola", display_name="Ola",
            is_organizer=True, email="ola@example.org")
        self.plain, self.plain_pw = create_member(
            organization=self.alpha, username="ada", display_name="Ada", email="ada@example.org")
        self.outsider, self.outsider_pw = create_member(
            organization=self.beta, username="bo", display_name="Bo", is_organizer=True, email="bo@example.org")
        set_tenant(None)

    def tearDown(self):
        set_tenant(None)

    def settle(self, member):
        """Clear the forced-change flag so a test can reach the rest of the app."""
        with tenant_context(member.organization):
            member.must_change_password = False
            member.save(update_fields=["must_change_password"])
        set_tenant(None)


class ForcedPasswordChange(MembersBase):
    def test_a_new_member_must_change_before_anything_else(self):
        self.assertTrue(self.plain.must_change_password)
        self.sign_in(self.plain.user)

        for path in ("/board/", "/ledger/", "/board/new/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertEqual(response["Location"], "/password/", path)

    def test_the_password_page_itself_is_reachable(self):
        self.sign_in(self.plain.user)
        self.assertEqual(self.client.get("/password/").status_code, 200)

    def test_signing_out_is_reachable(self):
        # Otherwise a member with an outstanding change is trapped.
        self.sign_in(self.plain.user)
        self.assertEqual(self.client.post("/logout/").status_code, 302)

    def test_changing_it_clears_the_flag_and_keeps_them_signed_in(self):
        self.sign_in(self.plain.user)
        response = self.client.post("/password/", {
            "old_password": self.plain_pw,
            "new_password1": "a-quiet-saturday-97",
            "new_password2": "a-quiet-saturday-97",
        })
        self.assertRedirects(response, "/board/")

        with tenant_context(self.alpha):
            self.plain.refresh_from_db()
            self.assertFalse(self.plain.must_change_password)
        set_tenant(None)

        # Still signed in: the session hash was updated, not invalidated.
        self.assertEqual(self.client.get("/board/").status_code, 200)

    def test_the_old_password_stops_working(self):
        self.sign_in(self.plain.user)
        self.client.post("/password/", {
            "old_password": self.plain_pw,
            "new_password1": "a-quiet-saturday-97",
            "new_password2": "a-quiet-saturday-97",
        })
        self.client.post("/logout/")

        refused = self.client.post(
            "/login/", {"username": "ada", "password": self.plain_pw})
        self.assertEqual(refused.status_code, 200)
        self.assertContains(refused, "do not match")


class OrganizerPrivilege(MembersBase):
    def setUp(self):
        super().setUp()
        self.settle(self.organizer)
        self.settle(self.plain)

    def test_an_organizer_sees_the_member_list(self):
        self.sign_in(self.organizer.user)
        response = self.client.get("/members/")
        self.assertContains(response, "Ada")
        self.assertContains(response, "Ola")

    def test_a_plain_member_may_not(self):
        self.sign_in(self.plain.user)
        self.assertEqual(self.client.get("/members/").status_code, 403)
        self.assertEqual(self.client.get("/members/new/").status_code, 403)

    def test_an_organizer_adds_somebody_and_sees_the_password_once(self):
        self.sign_in(self.organizer.user)
        response = self.client.post("/members/new/", {
            "username": "eir", "display_name": "Eir", "email": "eir@example.org",
        })
        self.assertEqual(response.status_code, 200)
        # Pull the credential actually rendered, so the reload check below is
        # about the credential and not about any word on the page.
        shown = re.search(r"<dt>Password</dt><dd>([^<]+)</dd>",
                          response.content.decode())
        self.assertIsNotNone(shown, "the one-time password was not displayed")
        password = shown.group(1).strip()

        with tenant_context(self.alpha):
            added = Member.objects.get(display_name="Eir")
            self.assertEqual(added.organization_id, self.alpha.id)
            self.assertTrue(added.must_change_password)
            self.assertFalse(added.is_organizer)
        set_tenant(None)

        # The credential is rendered, then gone. Assert on the credential, not
        # on the word: "Password" also appears in the nav link.
        again = self.client.get("/members/new/").content.decode()
        self.assertNotIn(password, again)
        self.assertNotIn("<dt>Password</dt>", again)

    def test_added_members_land_in_the_organizers_own_organization(self):
        # There is no organization field on the form, so this cannot be steered.
        self.sign_in(self.outsider.user)
        self.settle(self.outsider)
        self.sign_in(self.outsider.user)
        self.client.post("/members/new/", {
            "username": "nyx", "display_name": "Nyx", "email": "nyx@example.org"})

        with bypass_rls():
            nyx = Member.objects.get(display_name="Nyx")
            self.assertEqual(nyx.organization_id, self.beta.id)

    def test_the_member_list_never_shows_what_anyone_has_given(self):
        """no-aggregate-display, at the place it would feel most natural."""
        with tenant_context(self.alpha):
            posting = Posting.objects.create(
                organization=self.alpha, member=self.plain, description="Potatoes.")
            from site_app import services
            services.record_contribution(
                member=self.plain, posting=posting, hours=3)
        set_tenant(None)

        self.sign_in(self.organizer.user)
        body = self.client.get("/members/").content.decode().lower()
        for forbidden in ("3.00", "hours given", "total", "contributed"):
            self.assertNotIn(forbidden, body, forbidden)


class CreateMemberService(MembersBase):
    def test_a_duplicate_username_is_refused(self):
        with self.assertRaises(MemberExists):
            create_member(organization=self.alpha, username="ada", display_name="Ada 2", email="ada@example.org")

    def test_a_blank_username_is_refused(self):
        with self.assertRaises(ValueError):
            create_member(organization=self.alpha, username="   ", display_name="X", email="   @example.org")

    def test_the_generated_password_is_not_stored_in_readable_form(self):
        member, password = create_member(
            organization=self.alpha, username="sig", display_name="Sig", email="sig@example.org")
        user = User.objects.get(username="sig")
        self.assertNotIn(password, user.password)
        self.assertTrue(user.check_password(password))
