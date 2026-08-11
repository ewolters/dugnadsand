"""Second factor and federation SSO.

MFA is gated in middleware rather than inside the login view, so the default
for any route added later is protected. These tests hold that default, and hold
the SSO endpoint to refusing everything it cannot prove.
"""

import time
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from site_app.models import Member, Organization
from site_app.services_members import create_member
from site_app.tenancy import set_tenant, tenant_context


class AuthBase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(slug="alpha", name="Alpha Mutual Aid")
        self.member, self.password = create_member(
            organization=self.org, username="ada", display_name="Ada",
            email="ada@example.org")
        # These tests are about the second factor, not the first-run password.
        with tenant_context(self.org):
            self.member.must_change_password = False
            self.member.save(update_fields=["must_change_password"])
        set_tenant(None)

    def tearDown(self):
        set_tenant(None)

    def pass_mfa(self):
        session = self.client.session
        session["mfa_ok"] = True
        session.save()


class MFAGate(AuthBase):
    @mock.patch("kjerne_platform.mfa.is_enrolled", return_value=True)
    def test_an_enrolled_member_is_challenged_before_anything(self, _):
        self.client.force_login(self.member.user)
        for path in ("/board/", "/ledger/", "/members/", "/password/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertEqual(response["Location"], "/mfa/", path)

    @mock.patch("kjerne_platform.mfa.is_enrolled", return_value=False)
    def test_an_unenrolled_member_is_sent_to_set_it_up(self, _):
        self.client.force_login(self.member.user)
        response = self.client.get("/board/")
        self.assertEqual(response["Location"], "/mfa/setup/")

    @mock.patch("kjerne_platform.mfa.is_enrolled", return_value=True)
    def test_signing_out_stays_reachable(self, _):
        # Otherwise somebody who cannot produce a code is stuck.
        self.client.force_login(self.member.user)
        self.assertEqual(self.client.post("/logout/").status_code, 302)

    @mock.patch("kjerne_platform.mfa.is_enrolled", return_value=True)
    def test_the_public_pages_are_untouched(self, _):
        for path in ("/", "/attestation/", "/login/"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    @mock.patch("kjerne_platform.mfa.verify", return_value=True)
    @mock.patch("kjerne_platform.mfa.is_enrolled", return_value=True)
    def test_a_good_code_opens_the_app(self, _enrolled, _verify):
        self.client.force_login(self.member.user)
        response = self.client.post("/mfa/", {"code": "123456"})
        self.assertRedirects(response, "/board/")
        self.assertEqual(self.client.get("/board/").status_code, 200)

    @mock.patch("kjerne_platform.mfa.verify", return_value=False)
    @mock.patch("kjerne_platform.mfa.is_enrolled", return_value=True)
    def test_a_bad_code_does_not(self, _enrolled, _verify):
        self.client.force_login(self.member.user)
        response = self.client.post("/mfa/", {"code": "000000"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "did not match")
        self.assertEqual(self.client.get("/board/")["Location"], "/mfa/")

    @mock.patch("kjerne_platform.mfa.confirm", return_value=True)
    @mock.patch("kjerne_platform.mfa.enroll", return_value=("SECRET", "otpauth://totp/x"))
    @mock.patch("kjerne_platform.mfa.is_enrolled", return_value=False)
    def test_enrolling_confirms_and_lets_them_in(self, _e, _en, _c):
        self.client.force_login(self.member.user)
        response = self.client.post("/mfa/setup/", {"code": "123456"})
        self.assertRedirects(response, "/board/")

    def test_an_account_without_an_email_is_told_why_not(self):
        # MFA is keyed by email; looping such a person through a challenge they
        # cannot pass would be worse than saying so.
        self.member.user.email = ""
        self.member.user.save(update_fields=["email"])
        self.client.force_login(self.member.user)
        response = self.client.get("/mfa/setup/")
        self.assertContains(response, "no email address")


class EmailIsRequired(AuthBase):
    def test_a_member_cannot_be_created_without_one(self):
        with self.assertRaises(ValueError):
            create_member(organization=self.org, username="nope",
                          display_name="Nope", email="")


@override_settings()
class SSOEndpoint(AuthBase):
    SECRET = "test-sso-secret-value"

    def mint(self, **kw):
        from kjerne_platform import federation_sso
        params = dict(issuer="vault", email="ops@svend.ai", name="Ops",
                      teams=[], is_hub=True, now=int(time.time()),
                      jti=f"jti-{time.time_ns()}")
        params.update(kw)
        return federation_sso.mint_token(self.SECRET, **params)

    def test_a_valid_assertion_signs_somebody_in(self):
        with mock.patch.dict("os.environ", {"DUGNADSAND_SSO_SECRET": self.SECRET}):
            response = self.client.get("/sso/", {"token": self.mint()})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="ops@svend.ai").exists())

    def test_an_sso_user_is_not_a_member_of_anything(self):
        """The fail-closed answer to unresolved tier mapping.

        A federation operator gets a login and no Member row, so row-level
        security shows them nothing and every member route refuses. Guessing a
        mapping would put an outsider inside a community's ledger.
        """
        with mock.patch.dict("os.environ", {"DUGNADSAND_SSO_SECRET": self.SECRET}):
            self.client.get("/sso/", {"token": self.mint()})
        user = User.objects.get(username="ops@svend.ai")
        self.assertFalse(Member.objects.filter(user=user).exists())

        self.pass_mfa()
        self.assertEqual(self.client.get("/board/").status_code, 403)

    def test_a_forged_signature_is_refused(self):
        forged = self.mint()
        with mock.patch.dict("os.environ", {"DUGNADSAND_SSO_SECRET": "a-different-secret"}):
            response = self.client.get("/sso/", {"token": forged})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(username="ops@svend.ai").exists())

    def test_an_expired_assertion_is_refused(self):
        stale = self.mint(now=int(time.time()) - 3600, ttl=120)
        with mock.patch.dict("os.environ", {"DUGNADSAND_SSO_SECRET": self.SECRET}):
            self.assertEqual(self.client.get("/sso/", {"token": stale}).status_code, 400)

    def test_the_same_assertion_cannot_be_used_twice(self):
        token = self.mint()
        with mock.patch.dict("os.environ", {"DUGNADSAND_SSO_SECRET": self.SECRET}):
            first = self.client.get("/sso/", {"token": token})
            second = self.client.get("/sso/", {"token": token})
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 400)

    def test_an_unregistered_issuer_is_refused(self):
        token = self.mint(issuer="somebody-else")
        with mock.patch.dict("os.environ", {"DUGNADSAND_SSO_SECRET": self.SECRET}):
            self.assertEqual(self.client.get("/sso/", {"token": token}).status_code, 400)

    def test_it_refuses_when_no_secret_is_configured(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("DUGNADSAND_SSO_SECRET", None)
            self.assertEqual(self.client.get("/sso/", {"token": "x"}).status_code, 400)


class BothGatesTogether(AuthBase):
    """A brand-new member owes a second factor AND a password change.

    Each gate is correct alone. Together they deadlocked: MFA sent the member to
    /mfa/setup/, the password gate bounced that to /password/, and the MFA gate
    sent it back. This is the regression test for the pair.
    """

    def setUp(self):
        super().setUp()
        with tenant_context(self.org):
            self.member.must_change_password = True
            self.member.save(update_fields=["must_change_password"])
        set_tenant(None)

    @mock.patch("kjerne_platform.mfa.is_enrolled", return_value=False)
    def test_a_first_sign_in_does_not_loop(self, _):
        response = self.client.post(
            "/login/", {"username": "ada", "password": self.password}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain[-1][0], "/mfa/setup/")

    @mock.patch("kjerne_platform.mfa.confirm", return_value=True)
    @mock.patch("kjerne_platform.mfa.enroll", return_value=("SECRET", "otpauth://totp/x"))
    @mock.patch("kjerne_platform.mfa.is_enrolled", return_value=False)
    def test_after_the_second_factor_the_password_gate_takes_over(self, _e, _en, _c):
        self.client.force_login(self.member.user)
        self.client.post("/mfa/setup/", {"code": "123456"})

        # MFA satisfied; now the other gate should claim them, exactly once.
        response = self.client.get("/board/", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain[-1][0], "/password/")


class QRCode(AuthBase):
    """The setup page must offer something scannable.

    Without it a member has to hand-type a URI containing their shared secret,
    which is exactly the step people give up on.
    """

    @mock.patch("kjerne_platform.mfa.enroll",
                return_value=("ABC123",
                              "otpauth://totp/Dugnadsand:ada@example.org?secret=ABC123&issuer=Dugnadsand"))
    @mock.patch("kjerne_platform.mfa.is_enrolled", return_value=False)
    def test_the_setup_page_renders_a_scannable_code(self, _enrolled, _enroll):
        self.client.force_login(self.member.user)
        body = self.client.get("/mfa/setup/").content.decode()
        self.assertIn("<svg", body)
        self.assertIn("</svg>", body)

    @mock.patch("kjerne_platform.mfa.enroll",
                return_value=("ABC123",
                              "otpauth://totp/Dugnadsand:ada@example.org?secret=ABC123&issuer=Dugnadsand"))
    @mock.patch("kjerne_platform.mfa.is_enrolled", return_value=False)
    def test_the_key_is_still_offered_for_hand_entry(self, _enrolled, _enroll):
        # A camera that will not focus must not be the end of the road.
        self.client.force_login(self.member.user)
        body = self.client.get("/mfa/setup/").content.decode()
        self.assertIn("secret=ABC123", body)

    @mock.patch("site_app.auth_views._qr_svg", return_value=None)
    @mock.patch("kjerne_platform.mfa.enroll", return_value=("ABC123", "otpauth://totp/x?secret=ABC123"))
    @mock.patch("kjerne_platform.mfa.is_enrolled", return_value=False)
    def test_a_failed_render_degrades_instead_of_breaking(self, _e, _en, _qr):
        # qrcode missing or throwing must leave a usable page, not a 500.
        self.client.force_login(self.member.user)
        response = self.client.get("/mfa/setup/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("secret=ABC123", response.content.decode())


class EnrollmentIsStable(AuthBase):
    """Reloading setup must not kill the code somebody just scanned.

    mfa.enroll() overwrites any unconfirmed secret, so calling it per render
    meant a refresh - or a mistyped code, which re-renders this page - silently
    invalidated the QR already sitting in the member's authenticator app.
    """

    @mock.patch("kjerne_platform.mfa.is_enrolled", return_value=False)
    def test_a_reload_shows_the_same_secret(self, _):
        self.client.force_login(self.member.user)
        with mock.patch("kjerne_platform.mfa.enroll",
                        return_value=("S1", "otpauth://totp/x?secret=S1")) as enroll:
            first = self.client.get("/mfa/setup/").content.decode()
            second = self.client.get("/mfa/setup/").content.decode()

        enroll.assert_called_once()
        self.assertIn("secret=S1", first)
        self.assertIn("secret=S1", second)

    @mock.patch("kjerne_platform.mfa.verify", return_value=False)
    @mock.patch("kjerne_platform.mfa.confirm", return_value=False)
    @mock.patch("kjerne_platform.mfa.is_enrolled", return_value=False)
    def test_a_wrong_code_keeps_the_same_secret(self, _en, _c, _v):
        self.client.force_login(self.member.user)
        with mock.patch("kjerne_platform.mfa.enroll",
                        return_value=("S1", "otpauth://totp/x?secret=S1")) as enroll:
            self.client.get("/mfa/setup/")
            retry = self.client.post("/mfa/setup/", {"code": "000000"}).content.decode()

        enroll.assert_called_once()
        self.assertIn("secret=S1", retry)

    @mock.patch("kjerne_platform.mfa.is_enrolled", return_value=False)
    def test_the_uri_is_a_string_not_a_tuple(self, _):
        """enroll() returns (secret, uri). Rendering the pair would put the
        secret on the page twice and encode a Python repr into the QR."""
        self.client.force_login(self.member.user)
        with mock.patch("kjerne_platform.mfa.enroll",
                        return_value=("SEEKRIT", "otpauth://totp/x?secret=SEEKRIT")):
            body = self.client.get("/mfa/setup/").content.decode()
        self.assertNotIn("(&#x27;SEEKRIT&#x27;", body)
        self.assertIn("otpauth://totp/x?secret=SEEKRIT", body)


class EveryRouteIsAccountedFor(TestCase):
    """No route reaches a signed-out visitor unless it is meant to.

    Checking this by hand catches today's routes and nothing after them. The
    failure it prevents is dull and easy: somebody adds a view, forgets
    @login_required, and a member-only page answers 200 to the internet. This
    walks the URL conf, so a route added tomorrow is covered tomorrow.

    Making something public requires editing the list below, which is a visible
    decision in a diff rather than an omission nobody sees.
    """

    # Deliberately reachable without signing in, each for a stated reason.
    PUBLIC = {
        "": "the front page",
        "login/": "the way in",
        "logout/": "must work from a half-authenticated state",
        "how-it-works/": "the mechanics, for somebody deciding whether to use this",
        "policy/": "the operating policy; a board reads it before anybody has an account",
        "virtual-warehouse/": "how material moves; a business reads it before listing anything",
        "attestation/": "the proof; publishing it privately would defeat it",
        "chapters/": ("where chapters are and are not; somebody looking for "
                      "their own area has no account and should not need one"),
        "apply/": ("the ingress; an applicant has no account yet, and "
                   "requiring one to ask for admission is a closed door "
                   "wearing a form"),
        "act/<str:token>/": "the holder has no account — that is the whole point",
        "setup/<str:token>/": "used before an account has a password",
        "sso/": "the assertion IS the credential",
        "mfa/": "reached while signed in but not yet verified",
        "mfa/setup/": "same",
        "password/": "reached while owing a password change",
    }

    # Token-guarded rather than session-guarded; they answer 401 to a stranger.
    TOKEN_GUARDED = {"attestation/run/", "warehouse/sweep/"}

    def urls(self):
        from site_app import urls

        return [str(p.pattern) for p in urls.urlpatterns]

    def concrete(self, pattern):
        """A fetchable path, with any converter filled in."""
        import re

        path = re.sub(r"<uuid:[^>]+>", "00000000-0000-0000-0000-000000000000",
                      pattern)
        return "/" + re.sub(r"<str:[^>]+>", "x", path)

    def test_no_unlisted_route_answers_a_signed_out_visitor(self):
        leaked = []
        for pattern in self.urls():
            if pattern in self.PUBLIC or pattern in self.TOKEN_GUARDED:
                continue
            response = self.client.get(self.concrete(pattern))
            # 302 to login, 403, 404 for a missing object behind the gate, or
            # 405 for a POST-only route. Never 200.
            if response.status_code == 200:
                leaked.append(pattern)

        self.assertEqual(leaked, [], f"reachable without signing in: {leaked}")

    def test_the_public_list_has_not_gone_stale(self):
        """A route named public that no longer exists is a stale exemption
        somebody will copy the next time they add one."""
        patterns = set(self.urls())
        gone = sorted(set(self.PUBLIC) - patterns)
        self.assertEqual(gone, [], f"listed public but not routed: {gone}")

    def test_the_pages_meant_to_be_public_actually_are(self):
        """The other direction: an over-eager decorator would take the front
        page off the internet, and nothing else would notice."""
        for path in ("/", "/how-it-works/", "/attestation/", "/login/"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_the_scheduled_endpoints_refuse_a_stranger(self):
        for pattern in self.TOKEN_GUARDED:
            response = self.client.post("/" + pattern)
            self.assertEqual(response.status_code, 401, pattern)
