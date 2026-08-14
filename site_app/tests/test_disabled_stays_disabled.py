"""Turning an account off has to turn it off everywhere.

THE HOLE THIS CLOSES. `authenticate()` refuses an inactive user;
`auth_login()` does not. The password door goes through the first and the
federation door goes through the second, because there the assertion IS the
credential — so setting is_active=False shut the front door, left the side
door open, and looked from the front exactly like it had worked.

That is the worst shape a security bug can have: an operator disables an
account, sees the login refused, and reasonably concludes it is done.

Two doors call auth_login directly and both are covered here. Neither
re-enables the account: a disabled user arriving through the federation is
precisely the case this exists for, so it refuses rather than resurrects.
"""

import os
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase


class TheFrontDoor(TestCase):
    def test_a_disabled_account_cannot_sign_in_with_its_password(self):
        User.objects.create_user("hannah", password="dugnad-test-pw",
                                 is_active=False)
        response = self.client.post("/login/", {"username": "hannah",
                                                "password": "dugnad-test-pw"})
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_and_the_password_still_works_when_it_is_switched_back_on(self):
        """Off, not gone. The whole point of is_active over deletion is that
        it is one boolean back."""
        user = User.objects.create_user("hannah", password="dugnad-test-pw",
                                        is_active=False)
        User.objects.filter(pk=user.pk).update(is_active=True)

        response = self.client.post("/login/", {"username": "hannah",
                                                "password": "dugnad-test-pw"},
                                    follow=True)
        self.assertTrue(response.wsgi_request.user.is_authenticated)


class TheFederationDoor(TestCase):
    """The one that was open."""

    def sso(self, email):
        fake = SimpleNamespace(email=email)
        with patch.dict(os.environ, {"DUGNADSAND_SSO_SECRET": "s"}), \
             patch("kjerne_platform.federation_sso.verify_token",
                   return_value=fake):
            return self.client.get("/sso/?token=anything")

    def test_A_DISABLED_ACCOUNT_CANNOT_SIGN_IN_THROUGH_SSO(self):
        User.objects.create_user("h@example.test", email="h@example.test",
                                 password="dugnad-test-pw", is_active=False)
        response = self.sso("h@example.test")

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_signing_in_through_sso_does_not_re_enable_it(self):
        """Refused, not resurrected. An account that turned itself back on
        by being used would be no account control at all."""
        user = User.objects.create_user("h@example.test", email="h@example.test",
                                        password="dugnad-test-pw", is_active=False)
        self.sso("h@example.test")
        self.assertFalse(User.objects.get(pk=user.pk).is_active)

    def test_an_active_account_still_gets_through(self):
        """Guard the guard. A fix that shut the door on everybody would pass
        the test above and break the federation."""
        User.objects.create_user("ok@example.test", email="ok@example.test",
                                 password="dugnad-test-pw")
        response = self.sso("ok@example.test")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.wsgi_request.user.is_authenticated)


class TheSetupLinkDoor(TestCase):
    def test_a_setup_link_will_not_let_a_disabled_account_in(self):
        """A setup link is a credential somebody may still be holding when
        their account is turned off."""
        import inspect

        from site_app import auth_views

        source = inspect.getsource(auth_views.setup)
        self.assertIn("user.is_active", source)
