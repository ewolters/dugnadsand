"""Who "the operator" is, in the one place the terms send people to look.

The terms hand every joining organization an indemnity, a limitation of
liability and a warranty disclaimer, all of them running to "the operator",
and say the operator is the entity named at the foot of the page. For a while
the foot of the page named Dugnadsand, which is a network and not a person
anybody could indemnify.

So the name lives in configuration and is rendered by the chrome, in one place,
because the alternative is the same string typed into several templates and
only some of them updated when the entity changes.
"""

from django.test import TestCase, override_settings


class TheFooterNamesTheOperator(TestCase):
    def test_the_operator_appears_on_an_ordinary_page(self):
        self.assertContains(self.client.get("/terms/"), "SVEND, LLC")

    def test_it_is_the_configured_name_and_not_a_literal(self):
        with override_settings(OPERATOR_LEGAL_NAME="Some Other Entity, LLC"):
            response = self.client.get("/terms/")
        self.assertContains(response, "Some Other Entity, LLC")
        self.assertNotContains(response, "SVEND, LLC")

    def test_an_unset_operator_claims_nothing(self):
        """Better a missing line than a page asserting an entity that is not
        the one carrying the liability."""
        with override_settings(OPERATOR_LEGAL_NAME=""):
            response = self.client.get("/terms/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Operated by")


class TheSiteSaysOneThingAboutWhoRunsIt(TestCase):
    """The front page used to credit SVEND as a *sponsor* while the terms made
    the same party the *operator*. Those are different relationships — one
    funds a thing, the other runs it and answers for it — and a reader had no
    way to tell which was being claimed. Both now read the same value."""

    def test_the_front_page_does_not_call_the_operator_a_sponsor(self):
        self.assertNotContains(self.client.get("/"), "sponsored by")

    def test_the_front_page_names_the_same_party_as_the_terms(self):
        with override_settings(OPERATOR_LEGAL_NAME="Some Other Entity, LLC"):
            front = self.client.get("/")
            terms = self.client.get("/terms/")
        for response in (front, terms):
            self.assertContains(response, "Some Other Entity, LLC")
            self.assertNotContains(response, "SVEND")
