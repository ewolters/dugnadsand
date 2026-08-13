"""Signing in with what a person actually types.

Written after a real member lost an hour to it. Her username is "hannah";
a phone keyboard capitalises the first letter of a text field; Django's
ModelBackend matches exactly. Ten failures in under a minute, an IP ban for
an hour, and an error that reads as "your account does not exist".

The rule these hold: the software resolves what was typed, and NEVER tells
anybody whether an account exists.
"""

from django.contrib.auth.models import User
from django.test import TestCase

from site_app.models import Member, Organization
from site_app.tenancy import set_tenant, tenant_context

from .helpers import SignedIn

PASSWORD = "a-quiet-saturday-97"


class LoginBase(SignedIn, TestCase):
    def setUp(self):
        self.org = Organization.objects.create(slug="ouat", name="Once Upon a Table")
        self.user = User.objects.create_user(
            "hannah", email="onceuponatable.rentals@gmail.com", password=PASSWORD)
        with tenant_context(self.org):
            Member.objects.create(organization=self.org, display_name="Hannah",
                                  user=self.user)
        set_tenant(None)

    def tearDown(self):
        set_tenant(None)

    def attempt(self, username, password=PASSWORD):
        return self.client.post("/login/", {"username": username,
                                            "password": password})

    def signed_in(self, response):
        """A successful sign-in redirects; a refusal renders the form again."""
        return response.status_code == 302


class TheNameIsAcceptedHoweverItWasTyped(LoginBase):
    def test_exactly_as_stored(self):
        self.assertTrue(self.signed_in(self.attempt("hannah")))

    def test_capitalised_by_a_phone_keyboard(self):
        """THE ONE THAT COST AN HOUR."""
        self.assertTrue(self.signed_in(self.attempt("Hannah")))

    def test_shouted(self):
        self.assertTrue(self.signed_in(self.attempt("HANNAH")))

    def test_with_the_spaces_a_paste_brings(self):
        self.assertTrue(self.signed_in(self.attempt("  hannah ")))

    def test_the_email_address_works_too(self):
        """The address is the thing people know about themselves."""
        self.assertTrue(
            self.signed_in(self.attempt("onceuponatable.rentals@gmail.com")))

    def test_the_email_address_however_cased(self):
        self.assertTrue(
            self.signed_in(self.attempt("OnceUponATable.Rentals@Gmail.com")))

    def test_the_field_does_not_ask_the_keyboard_to_capitalise(self):
        """The fix at source. The view resolving it is the backstop, because
        the attribute is a hint a browser may ignore."""
        body = self.client.get("/login/").content.decode()
        self.assertIn('autocapitalize="none"', body)


class ItStillRefusesWhatItShould(LoginBase):
    def test_a_wrong_password_is_refused(self):
        self.assertFalse(self.signed_in(self.attempt("hannah", "wrong")))

    def test_an_unknown_name_is_refused(self):
        self.assertFalse(self.signed_in(self.attempt("nobody")))

    def test_the_refusal_is_identical_either_way(self):
        """Never a different answer for "no such account" than for "wrong
        password". A difference there is a way to enumerate the membership,
        which on this site is a list of who is in a mutual aid network."""
        unknown = self.attempt("nobody").content.decode()
        wrong = self.attempt("hannah", "wrong").content.decode()
        self.assertIn("do not match", unknown)
        self.assertIn("do not match", wrong)

    def test_ambiguity_fails_closed(self):
        """Two accounts differing only by case: nothing is guessed."""
        User.objects.create_user("HANNAH", password="another-password-entirely")
        self.assertFalse(self.signed_in(self.attempt("hAnNaH")))

    def test_an_address_matching_two_accounts_resolves_to_neither(self):
        User.objects.create_user(
            "second", email="onceuponatable.rentals@gmail.com",
            password="another-password-entirely")
        self.assertFalse(
            self.signed_in(self.attempt("onceuponatable.rentals@gmail.com")))

    def test_an_exact_username_wins_over_somebody_elses_address(self):
        """If one person's username is another's email, the username is the
        stronger claim and is matched first."""
        User.objects.create_user("shared@example.test", password=PASSWORD)
        User.objects.create_user(
            "other", email="shared@example.test", password="different")

        response = self.attempt("shared@example.test")
        self.assertTrue(self.signed_in(response))
