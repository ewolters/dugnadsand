"""Getting into the network.

Two things are being held here. The first is that rigour actually bites: an
unverified credential, an expired one, an unscreened individual and an
unagreed policy each refuse admission, and each says so by name.

The second is what is NOT asked. An applicant proves they are a real and
identifiable party. Nothing asks what they offer or how good they are at it,
because a system that graded offers would be pricing them.
"""

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase

from site_app.models import Application, Credential, Region, Screening
from site_app.services_applications import (REQUIRED, NotReady, admit,
                                            decline, record_screening, submit,
                                            verify_credential)


class ApplicationBase(TestCase):
    def setUp(self):
        self.region = Region.objects.create(
            slug="upstate-sc", name="Upstate South Carolina")
        self.reviewer = User.objects.create_user(
            "reviewer", password="dugnad-test-pw")

    def a_business(self, **kw):
        return submit(
            kind=Application.BUSINESS, region=self.region,
            legal_name="Alderman Electric LLC", contact_name="Dana Alderman",
            email="dana@example.test", statement="We wire things.",
            agreed=True,
            credentials={
                "Business license": {
                    "authority": "SC LLR", "reference": "EL-44821",
                    "expires_on": date.today() + timedelta(days=200)},
                "Certificate of insurance": {
                    "authority": "Cypress Mutual", "reference": "CGL-9912",
                    "expires_on": date.today() + timedelta(days=90)},
                "Tax identification number": {"reference": "57-1234567"},
            }, **kw)

    def verify_all(self, application, expires=None):
        for credential in application.credentials.all():
            verify_credential(credential=credential, user=self.reviewer,
                              verified_on=date.today(), expires_on=expires)


class WhatEachKindMustProduce(ApplicationBase):
    def test_a_business_owes_a_licence_insurance_and_a_tax_number(self):
        application = self.a_business()
        self.assertEqual(
            sorted(c.kind for c in application.credentials.all()),
            ["Business license", "Certificate of insurance",
             "Tax identification number"])

    def test_a_not_for_profit_owes_a_determination_letter_and_a_tax_number(self):
        application = submit(
            kind=Application.NONPROFIT, legal_name="Rivertown Trust",
            contact_name="Sam", email="sam@example.test",
            statement="We run a food bank.", agreed=True,
            credentials={"IRS determination letter": {"reference": "DL-2201"},
                         "Tax identification number": {"reference": "57-7654321"}})
        self.assertEqual(
            sorted(c.kind for c in application.credentials.all()),
            ["IRS determination letter", "Tax identification number"])

    def test_an_individual_owes_no_documents_at_all(self):
        application = submit(
            kind=Application.INDIVIDUAL, legal_name="Ola Nilsen",
            contact_name="Ola Nilsen", email="ola@example.test",
            statement="I have a truck and Saturdays.", agreed=True)
        self.assertEqual(application.credentials.count(), 0)

    def test_a_row_is_created_even_when_the_applicant_supplied_nothing(self):
        """An omission has to be a visible outstanding row.

        If a missing licence number simply meant no Credential existed, the
        review would be checking a list that shortened itself whenever
        somebody left a box empty.
        """
        application = submit(
            kind=Application.BUSINESS, legal_name="Quiet Trading Co",
            contact_name="Pat", email="pat@example.test",
            statement="Nothing supplied.", agreed=True)
        self.assertEqual(application.credentials.count(), 3)
        self.assertEqual(len(application.outstanding), 3)

    def test_nothing_asks_what_the_applicant_offers(self):
        """The distinction the whole ingress rests on.

        An electrician proves a licence. No field rates, tiers, prices or
        describes their work -- see no-catalog and no-material-valuation, both
        of which exist to stop exactly this becoming a marketplace.
        """
        names = {f.name for f in Application._meta.get_fields()}
        for forbidden in ("services", "offering", "offers", "trade", "skills",
                          "category", "rate", "rating", "tier", "price",
                          "hourly", "capacity", "score"):
            self.assertNotIn(forbidden, names, f"Application grew {forbidden}")

    def test_no_credential_carries_a_value(self):
        names = {f.name for f in Credential._meta.get_fields()}
        for forbidden in ("value", "price", "cost", "amount", "hours", "rate"):
            self.assertNotIn(forbidden, names, f"Credential grew {forbidden}")


class AdmissionRefusesUntilItIsProved(ApplicationBase):
    def test_an_unverified_credential_blocks_and_is_named(self):
        application = self.a_business()
        with self.assertRaises(NotReady) as caught:
            admit(application=application, user=self.reviewer)
        self.assertIn("Business license not verified", str(caught.exception))

    def test_verifying_everything_releases_it(self):
        application = self.a_business()
        self.verify_all(application)
        admit(application=application, user=self.reviewer)

        fresh = Application.objects.get(pk=application.pk)
        self.assertTrue(fresh.admitted)
        self.assertEqual(fresh.decided_by, self.reviewer)

    def test_an_expired_credential_blocks_even_though_it_was_verified(self):
        """The failure nobody catches: the row was filled in correctly, two
        years ago. A licence that ran out in March is not a licence."""
        application = self.a_business()
        self.verify_all(application)
        stale = application.credentials.get(kind="Business license")
        stale.expires_on = date.today() - timedelta(days=1)
        stale.save(update_fields=["expires_on"])

        with self.assertRaises(NotReady) as caught:
            admit(application=Application.objects.get(pk=application.pk),
                  user=self.reviewer)
        self.assertIn("Business license expired", str(caught.exception))

    def test_a_credential_with_no_expiry_never_lapses(self):
        """A tax number does not run out, and treating it as though it did
        would make the check cry wolf until people routed around it."""
        application = self.a_business()
        self.verify_all(application)
        tax = application.credentials.get(kind="Tax identification number")
        self.assertIsNone(tax.expires_on)
        self.assertFalse(tax.lapsed)

    def test_an_individual_is_blocked_until_somebody_has_looked(self):
        application = submit(
            kind=Application.INDIVIDUAL, legal_name="Ola Nilsen",
            contact_name="Ola Nilsen", email="ola@example.test",
            statement="I have a truck.", agreed=True)

        with self.assertRaises(NotReady) as caught:
            admit(application=application, user=self.reviewer)
        self.assertIn("no clear screening on file", str(caught.exception))

        record_screening(
            application=application, user=self.reviewer,
            source="National Sex Offender Public Website",
            searched_name="Ola Nilsen", searched_on=date.today(), clear=True)
        admit(application=Application.objects.get(pk=application.pk),
              user=self.reviewer)

    def test_a_screening_that_found_something_does_not_clear_it(self):
        """clear=False means a person needs to look, and admission stays
        blocked until somebody records a clear search or declines."""
        application = submit(
            kind=Application.INDIVIDUAL, legal_name="Ola Nilsen",
            contact_name="Ola Nilsen", email="ola@example.test",
            statement="I have a truck.", agreed=True)
        record_screening(
            application=application, user=self.reviewer, source="A registry",
            searched_name="Ola Nilsen", searched_on=date.today(), clear=False,
            note="A name match that needs a person.")

        with self.assertRaises(NotReady):
            admit(application=Application.objects.get(pk=application.pk),
                  user=self.reviewer)

    def test_an_unagreed_policy_blocks(self):
        application = submit(
            kind=Application.INDIVIDUAL, legal_name="Ola Nilsen",
            contact_name="Ola", email="ola@example.test",
            statement="I have a truck.", agreed=False)
        record_screening(
            application=application, user=self.reviewer, source="A registry",
            searched_name="Ola", searched_on=date.today(), clear=True)

        with self.assertRaises(NotReady) as caught:
            admit(application=Application.objects.get(pk=application.pk),
                  user=self.reviewer)
        self.assertIn("policy has not been agreed", str(caught.exception))

    def test_declining_is_always_permitted(self):
        """A refusal needs no paperwork to be complete. Requiring a full file
        before saying no would mean chasing documents for an applicant already
        being turned down."""
        application = self.a_business()
        self.assertTrue(application.blockers)
        decline(application=application, user=self.reviewer, note="Out of area.")
        self.assertFalse(Application.objects.get(pk=application.pk).admitted)

    def test_every_blocker_is_named_not_just_the_first(self):
        application = self.a_business()
        with self.assertRaises(NotReady) as caught:
            admit(application=application, user=self.reviewer)
        self.assertEqual(len(caught.exception.blockers), 3)


class WhatIsAgreedTo(ApplicationBase):
    def test_the_manifest_version_is_recorded_not_a_bare_yes(self):
        """So that changing a commitment later cannot silently
        re-characterise what somebody already signed."""
        from policy.attest import load_manifest

        application = self.a_business()
        self.assertEqual(application.agreed_policy_version,
                         str(load_manifest()["manifest"]["version"]))
        self.assertIsNotNone(application.agreed_at)


class TheScreeningRecordDoesNotDecide(ApplicationBase):
    """It records that a person looked. It does not match anybody itself.

    Matching a name against a public registry produces false positives on
    common names, and wiring a match straight into a refusal means somebody is
    turned away by a string comparison nobody reviewed.
    """

    def test_it_records_what_was_searched_and_by_whom(self):
        application = submit(
            kind=Application.INDIVIDUAL, legal_name="Ola Nilsen",
            contact_name="Ola", email="ola@example.test",
            statement="A truck.", agreed=True)
        screening = record_screening(
            application=application, user=self.reviewer,
            source="National Sex Offender Public Website",
            searched_name="Ola Nilsen", searched_on=date.today(), clear=True)

        self.assertEqual(screening.searched_by, self.reviewer)
        self.assertEqual(screening.source,
                         "National Sex Offender Public Website")

    def test_the_model_holds_no_automated_match(self):
        """No score, no confidence, no provider. A field like that is where an
        automatic refusal would arrive."""
        names = {f.name for f in Screening._meta.get_fields()}
        for forbidden in ("score", "confidence", "match", "provider",
                          "automatic", "result_code", "risk"):
            self.assertNotIn(forbidden, names, f"Screening grew {forbidden}")


class TheApplicationPage(ApplicationBase):
    def test_the_form_is_public(self):
        self.assertEqual(self.client.get("/apply/").status_code, 200)

    def test_a_blind_post_is_refused(self):
        """No stamp means the form was never rendered, which is a script."""
        response = self.client.post("/apply/", {
            "kind": Application.INDIVIDUAL, "legal_name": "Bot",
            "contact_name": "Bot", "email": "bot@example.test",
            "statement": "x", "agreed": "on"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Application.objects.count(), 0)

    def test_a_business_is_told_what_it_is_missing_on_the_page(self):
        from site_app.forms import ApplicationForm

        response = self.client.post("/apply/", {
            "kind": Application.BUSINESS, "legal_name": "Alderman Electric",
            "contact_name": "Dana", "email": "dana@example.test",
            "statement": "We wire things.", "agreed": "on",
            "t": ApplicationForm.stamp()})
        body = response.content.decode()
        self.assertEqual(Application.objects.count(), 0)
        self.assertIn("A business needs its", body)

    def test_an_individual_is_not_asked_for_a_licence(self):
        from site_app.forms import ApplicationForm

        import time

        stamp = ApplicationForm.stamp()
        time.sleep(2.1)
        response = self.client.post("/apply/", {
            "kind": Application.INDIVIDUAL, "legal_name": "Ola Nilsen",
            "contact_name": "Ola Nilsen", "email": "ola@example.test",
            "statement": "I have a truck and Saturdays.", "agreed": "on",
            "t": stamp})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Application.objects.count(), 1)

    def test_the_page_says_submitting_admits_nobody(self):
        import re

        body = re.sub(r"\s+", " ", self.client.get("/apply/").content.decode())
        self.assertIn("It admits nobody", body)

    def test_the_page_does_not_ask_what_is_offered(self):
        body = self.client.get("/apply/").content.decode().lower()
        for forbidden in ('name="services"', 'name="rate"', 'name="category"',
                          'name="tier"'):
            self.assertNotIn(forbidden, body)


class ThePersonalDataIsSealed(ApplicationBase):
    """Read the raw column, not the model.

    Asserting through the ORM proves nothing: from_db_value decrypts on the
    way out, so a field that was never encrypted and one that round-trips
    perfectly look identical from Python. The only honest check is what
    Postgres is actually holding.
    """

    def raw(self, table, column, pk):
        from django.db import connection

        with connection.cursor() as cur:
            cur.execute(f"SELECT {column} FROM {table} WHERE id = %s", [str(pk)])
            return cur.fetchone()[0]

    def test_the_applicants_details_are_not_stored_in_the_clear(self):
        application = self.a_business()
        for column, plaintext in (("legal_name", "Alderman Electric LLC"),
                                  ("contact_name", "Dana Alderman"),
                                  ("email", "dana@example.test"),
                                  ("statement", "We wire things.")):
            stored = self.raw("site_app_application", column, application.pk)
            self.assertNotIn(plaintext, stored, column)
            self.assertTrue(stored.startswith("gAAAAA"),
                            f"{column} is not a Fernet token")

    def test_the_tax_number_is_not_stored_in_the_clear(self):
        """The single most sensitive value this system holds."""
        application = self.a_business()
        credential = application.credentials.get(kind="Tax identification number")
        stored = self.raw("site_app_credential", "reference", credential.pk)
        self.assertNotIn("57-1234567", stored)

    def test_a_screened_persons_name_is_not_stored_in_the_clear(self):
        application = submit(
            kind=Application.INDIVIDUAL, legal_name="Ola Nilsen",
            contact_name="Ola", email="ola@example.test",
            statement="A truck.", agreed=True)
        screening = record_screening(
            application=application, user=self.reviewer, source="A registry",
            searched_name="Ola Nilsen", searched_on=date.today(), clear=True)
        stored = self.raw("site_app_screening", "searched_name", screening.pk)
        self.assertNotIn("Ola Nilsen", stored)

    def test_it_still_reads_back_correctly(self):
        """Guard the guard: ciphertext nobody can decrypt is not privacy, it
        is data loss."""
        application = self.a_business()
        fresh = Application.objects.get(pk=application.pk)
        self.assertEqual(fresh.legal_name, "Alderman Electric LLC")
        self.assertEqual(fresh.email, "dana@example.test")
        self.assertEqual(
            fresh.credentials.get(kind="Tax identification number").reference,
            "57-1234567")

    def test_what_the_review_queries_on_stays_readable(self):
        """kind and source are plaintext on purpose. Ciphertext does not
        compare, so encrypting these would make the lookups in
        decide_application match nothing, silently, forever."""
        application = self.a_business()
        self.assertEqual(
            self.raw("site_app_credential", "kind",
                     application.credentials.get(kind="Business license").pk),
            "Business license")
        self.assertEqual(
            self.raw("site_app_application", "kind", application.pk),
            Application.BUSINESS)


class WhoIsTold(ApplicationBase):
    def test_the_applicant_is_acknowledged_on_submitting(self):
        from unittest.mock import patch

        from site_app.forms import ApplicationForm
        import time

        stamp = ApplicationForm.stamp()
        time.sleep(2.1)
        with patch("kjerne_platform.email.send", return_value=1) as send:
            self.client.post("/apply/", {
                "kind": Application.INDIVIDUAL, "legal_name": "Ola Nilsen",
                "contact_name": "Ola Nilsen", "email": "ola@example.test",
                "statement": "I have a truck.", "agreed": "on", "t": stamp})

        recipients = [c.kwargs["to"] for c in send.call_args_list]
        self.assertIn("ola@example.test", recipients)

    def test_the_acknowledgement_does_not_quote_the_statement_back(self):
        from unittest.mock import patch

        application = self.a_business()
        with patch("kjerne_platform.email.send", return_value=1) as send:
            from site_app.services_applications import acknowledge
            acknowledge(application)

        self.assertNotIn("We wire things.", send.call_args.kwargs["body"])

    def test_the_reviewer_is_told_a_record_exists_and_nothing_in_it(self):
        """The same rule the app's own notifications follow. An inbox does not
        need a second copy of somebody's tax number."""
        from unittest.mock import patch

        from site_app.services_applications import tell_the_reviewer

        application = self.a_business()
        with patch("kjerne_platform.email.send", return_value=1) as send:
            tell_the_reviewer(application, inbox="review@example.test")

        body = send.call_args.kwargs["body"]
        self.assertIn(str(application.id), body)
        for leaked in ("Alderman Electric LLC", "Dana Alderman",
                       "dana@example.test", "57-1234567", "We wire things."):
            self.assertNotIn(leaked, body, leaked)

    def test_no_reviewer_mail_goes_out_when_no_inbox_is_configured(self):
        from unittest.mock import patch

        from site_app.services_applications import tell_the_reviewer

        with patch("kjerne_platform.email.send") as send:
            tell_the_reviewer(self.a_business(), inbox=None)
        send.assert_not_called()

    def test_an_admitted_applicant_is_told(self):
        from unittest.mock import patch

        from site_app.services_applications import tell_decision

        application = self.a_business()
        self.verify_all(application)
        admit(application=application, user=self.reviewer)
        with patch("kjerne_platform.email.send", return_value=1) as send:
            tell_decision(application)

        self.assertEqual(send.call_args.kwargs["to"], "dana@example.test")
        self.assertIn("accepted", send.call_args.kwargs["body"])

    def test_a_declined_applicant_is_told_without_the_internal_note(self):
        """decision_note is written for the review, in shorthand, and
        forwarding it would publish it."""
        from unittest.mock import patch

        from site_app.services_applications import tell_decision

        application = self.a_business()
        decline(application=application, user=self.reviewer,
                note="Could not reach them twice; Dana sounded unsure.")
        with patch("kjerne_platform.email.send", return_value=1) as send:
            tell_decision(application)

        body = send.call_args.kwargs["body"]
        self.assertIn("not been taken forward", body)
        self.assertNotIn("sounded unsure", body)

    def test_an_undecided_application_tells_nobody(self):
        from unittest.mock import patch

        from site_app.services_applications import tell_decision

        with patch("kjerne_platform.email.send") as send:
            tell_decision(self.a_business())
        send.assert_not_called()

    def test_a_mail_failure_does_not_lose_the_application(self):
        """The property the ordering exists for. An application recorded but
        unacknowledged is recoverable; one lost to a mail outage is not."""
        from unittest.mock import patch

        from site_app.forms import ApplicationForm
        import time

        stamp = ApplicationForm.stamp()
        time.sleep(2.1)
        with patch("kjerne_platform.email.send",
                   side_effect=RuntimeError("queue is down")):
            response = self.client.post("/apply/", {
                "kind": Application.INDIVIDUAL, "legal_name": "Ola Nilsen",
                "contact_name": "Ola Nilsen", "email": "ola@example.test",
                "statement": "I have a truck.", "agreed": "on", "t": stamp})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Application.objects.count(), 1)
