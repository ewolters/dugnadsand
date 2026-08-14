"""The agreement — the only contract on the site.

Three documents do three jobs and the distinction is load-bearing:

  /policy/ describes what the software does, and every commitment on it is
  bound to a check that runs against the source.

  /acceptable-use/ is the standard of conduct applied by people, and says so,
  because there is no executable check for whether a posting is campaigning.

  /terms/ is what an organization AGREES TO. It allocates responsibility.

Conflating them is the failure this file guards. The agreement used to point
at /policy/ alone, which meant organizations were agreeing to an engineering
manifest and to nothing that said who answers when something goes wrong.

VERSIONED SEPARATELY, for the same reason. Bumping the terms because a check
was refactored would re-ask everybody to agree for no reason; bumping the
manifest because a clause was edited would move a contract underneath
somebody quietly.
"""

import re

from django.test import TestCase

from site_app.models import Application
from site_app.services_applications import (TERMS_VERSION, policy_version,
                                            submit, terms_version)


def prose(body):
    body = re.sub(r"<(script|style)\b.*?</\1>", " ", body, flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))


class ThePageExists(TestCase):
    def test_it_is_public(self):
        """Somebody deciding whether to apply has to be able to read what
        they would be agreeing to, without an account."""
        self.assertEqual(self.client.get("/terms/").status_code, 200)

    def test_it_states_its_own_version(self):
        response = self.client.get("/terms/")
        self.assertContains(response, f"Version {TERMS_VERSION}")

    def test_it_is_linked_from_the_footer_of_every_public_page(self):
        for path in ("/", "/how-it-works/", "/policy/", "/acceptable-use/",
                     "/need-help/", "/apply/"):
            with self.subTest(path=path):
                self.assertContains(self.client.get(path), 'href="/terms/"')


class WhatItHasToSay(TestCase):
    """The clauses that carry the liability posture.

    Asserted on prose rather than markup, and phrase by phrase, because the
    whole value of this page is that specific sentences are on it.
    """

    def setUp(self):
        self.prose = prose(self.client.get("/terms/").content.decode())

    def test_admission_is_registration_not_endorsement(self):
        self.assertIn("Admission is registration, not endorsement", self.prose)
        self.assertIn("does not confirm it and does not vouch for it",
                      self.prose)

    def test_the_organization_carries_its_own_insurance_and_licences(self):
        self.assertIn("Its own insurance", self.prose)
        self.assertIn("Its own licences", self.prose)

    def test_somebody_who_asks_for_help_is_not_a_party(self):
        """The structural claim the whole design rests on. If this sentence
        ever leaves the page, the design has changed and nobody noticed."""
        self.assertIn("is not a party to these terms", self.prose)
        self.assertIn("records no outcome", self.prose)

    def test_there_is_an_indemnity(self):
        self.assertIn("will indemnify the operator", self.prose)

    def test_the_indemnity_carves_out_the_operator_s_own_negligence(self):
        """An indemnity that swallows the operator's own negligence is the
        kind a court strikes, which would leave nothing rather than less."""
        self.assertIn("own negligence or wilful misconduct", self.prose)

    def test_liability_is_limited_and_says_what_it_cannot_exclude(self):
        self.assertIn("indirect or consequential loss", self.prose)
        self.assertIn("death or personal injury", self.prose)

    def test_it_creates_no_agency(self):
        self.assertIn("no partnership, joint venture, employment", self.prose)

    def test_it_commits_to_erasing_the_contact(self):
        """A retention promise belongs in the agreement and not only in the
        code, because the code can change without anybody being told."""
        self.assertIn("erased when the request", self.prose)
        self.assertIn("ninety days", self.prose)

    def test_it_names_a_governing_law(self):
        self.assertIn("South Carolina", self.prose)


class WhatIsAgreedIsRecorded(TestCase):
    def test_submitting_records_the_terms_version(self):
        application = submit(
            kind=Application.BUSINESS, legal_name="Alderman Electric LLC",
            contact_name="Dana", email="dana@example.test",
            statement="We wire things.", agreed=True)
        self.assertEqual(application.agreed_terms_version, TERMS_VERSION)

    def test_not_agreeing_records_nothing(self):
        application = submit(
            kind=Application.BUSINESS, legal_name="Alderman Electric LLC",
            contact_name="Dana", email="dana@example.test",
            statement="We wire things.", agreed=False)
        self.assertEqual(application.agreed_terms_version, "")

    def test_the_two_versions_are_independent(self):
        """Not equality — INDEPENDENCE. They happen to both be "1" today,
        and a test asserting they match would pass now and enforce exactly
        the coupling this separation exists to prevent."""
        import inspect

        from site_app import services_applications

        source = inspect.getsource(services_applications.terms_version)
        self.assertNotIn("manifest", source)
        self.assertNotIn("policy_version", source)


class TheAgreementPointsAtTheAgreement(TestCase):
    def test_the_apply_page_links_the_terms_beside_the_checkbox(self):
        """It linked /policy/ alone, so an applicant ticking the box was
        agreeing to an engineering manifest."""
        body = self.client.get("/apply/").content.decode()
        agreement = body[body.index('class="agree"'):]
        self.assertIn('href="/terms/"', agreement)
        self.assertIn('href="/acceptable-use/"', agreement)

    def test_the_label_says_what_is_being_agreed(self):
        from site_app.forms import ApplicationForm

        label = ApplicationForm().fields["agreed"].label
        self.assertIn("terms of participation", label)
        self.assertIn("acceptable use", label)
