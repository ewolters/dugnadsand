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


class AdmissionTurnsOnAgreementNotOnProof(ApplicationBase):
    """Retargeted when vetting-as-certification was dropped.

    This class asserted that admission was refused until every credential had
    been verified and nothing had expired. That was a stronger gate and a
    worse idea: verifying a licence and recording that we checked is a
    REPRESENTATION TO EVERYBODY ELSE, and a network that vouches for its
    members owns what they do in a way one that registers them does not.

    The tools survive and an officer still sees what nobody has looked at.
    What is gone is the system withholding admission until somebody vouches.
    """

    def test_an_unchecked_credential_does_NOT_block(self):
        application = self.a_business()
        admit(application=application, user=self.reviewer)
        self.assertTrue(Application.objects.get(pk=application.pk).admitted)

    def test_but_the_officer_is_still_told_nobody_looked(self):
        """Dropping the gate must not drop the information. A person
        deciding wants to know that nobody opened the insurance
        certificate — they simply are not overruled by a machine."""
        application = self.a_business()
        notes = " ".join(application.unchecked)
        self.assertIn("Business license", notes)
        self.assertIn("nobody has looked at this", notes)

    def test_verifying_everything_releases_it(self):
        application = self.a_business()
        self.verify_all(application)
        admit(application=application, user=self.reviewer)

        fresh = Application.objects.get(pk=application.pk)
        self.assertTrue(fresh.admitted)
        self.assertEqual(fresh.decided_by, self.reviewer)

    def test_an_expired_credential_does_not_block_either(self):
        """It is still surfaced, and a person can still decline on it. What
        it no longer does is refuse on the system's behalf, which would be
        the system asserting it knows the licence is dead."""
        application = self.a_business()
        self.verify_all(application)
        stale = application.credentials.get(kind="Business license")
        stale.expires_on = date.today() - timedelta(days=1)
        stale.save(update_fields=["expires_on"])

        fresh = Application.objects.get(pk=application.pk)
        admit(application=fresh, user=self.reviewer)
        self.assertTrue(Application.objects.get(pk=application.pk).admitted)
        self.assertTrue(any("the date on it passed" in u for u in fresh.unchecked))

    def test_a_credential_with_no_expiry_never_lapses(self):
        """A tax number does not run out, and treating it as though it did
        would make the check cry wolf until people routed around it."""
        application = self.a_business()
        self.verify_all(application)
        tax = application.credentials.get(kind="Tax identification number")
        self.assertIsNone(tax.expires_on)
        self.assertFalse(tax.lapsed)

    def test_an_individual_is_not_blocked_by_the_absence_of_a_search(self):
        """A recorded search is a representation like any other. The tool
        stays and an officer who runs one has it on the record; the system
        no longer refuses on its behalf."""
        application = submit(
            kind=Application.INDIVIDUAL, legal_name="Ola Nilsen",
            contact_name="Ola Nilsen", email="ola@example.test",
            statement="I have a truck.", agreed=True)

        self.assertIn("no clear screening on file", application.unchecked)
        admit(application=application, user=self.reviewer)
        self.assertTrue(Application.objects.get(pk=application.pk).admitted)

    def test_a_screening_that_found_something_is_still_recorded(self):
        """clear=False used to block. It now says a person should look, to
        the person who is looking, which is all it ever really did."""
        application = submit(
            kind=Application.INDIVIDUAL, legal_name="Ola Nilsen",
            contact_name="Ola Nilsen", email="ola@example.test",
            statement="I have a truck.", agreed=True)
        record_screening(
            application=application, user=self.reviewer, source="A registry",
            searched_name="Ola Nilsen", searched_on=date.today(), clear=False,
            note="A name match that needs a person.")

        fresh = Application.objects.get(pk=application.pk)
        self.assertIn("no clear screening on file", fresh.unchecked)
        self.assertFalse(fresh.screenings.filter(clear=True).exists())


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
        """Unchanged in substance: a refusal needs no paperwork to be
        complete. It is asserted against an application that could not be
        admitted, which is now the un-agreed one."""
        application = submit(
            kind=Application.BUSINESS, legal_name="Alderman Electric LLC",
            contact_name="Dana", email="dana@example.test",
            statement="We wire things.", agreed=False)

        decline(application=application, user=self.reviewer)
        self.assertFalse(Application.objects.get(pk=application.pk).admitted)


    def test_the_one_remaining_blocker_is_the_agreement(self):
        """Six reasons became one, and that one is a contract rather than a
        claim: they agreed to the policy. Everything else that used to
        refuse was the network vouching for somebody."""
        application = submit(
            kind=Application.BUSINESS, legal_name="Alderman Electric LLC",
            contact_name="Dana", email="dana@example.test",
            statement="We wire things.", agreed=False,
            credentials={"Business license": {"reference": "EL-1"}})

        self.assertEqual(application.blockers,
                         ["the policy has not been agreed"])
        with self.assertRaises(NotReady):
            admit(application=application, user=self.reviewer)


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


class AdmittingBuildsTheFrontDoor(ApplicationBase):
    """A yes used to end with a printed list of three more commands, which
    meant an accepted applicant waited while somebody remembered to run them.
    """

    def ready_business(self):
        application = self.a_business()
        self.verify_all(application)
        return Application.objects.get(pk=application.pk)

    def admit_it(self, application, **kw):
        from unittest.mock import patch

        from site_app.services_applications import admit_to_network

        with patch("kjerne_platform.email.send", return_value=1) as send:
            made = admit_to_network(application=application,
                                    user=self.reviewer, **kw)
        return made, send

    def test_it_creates_the_organization_in_the_right_chapter(self):
        from site_app.models import Organization

        made, _ = self.admit_it(self.ready_business())
        organization = Organization.objects.get(slug="alderman-electric-llc")

        self.assertEqual(organization.name, "Alderman Electric LLC")
        self.assertEqual(organization.region, self.region)
        self.assertEqual(made["organization"], organization)

    def test_it_creates_the_first_member_from_the_contact(self):
        from site_app.tenancy import tenant_context

        made, _ = self.admit_it(self.ready_business())
        with tenant_context(made["organization"]):
            member = made["member"]
            self.assertEqual(member.display_name, "Dana Alderman")
            self.assertEqual(member.user.email, "dana@example.test")
            # Somebody has to be able to add the rest, and there is nobody else.
            self.assertTrue(member.is_organizer)

    def test_the_username_is_derived_from_the_email(self):
        made, _ = self.admit_it(self.ready_business())
        self.assertEqual(made["member"].user.username, "dana")

    def test_a_taken_username_gets_a_suffix_rather_than_failing(self):
        from django.contrib.auth.models import User

        User.objects.create_user("dana", password="dugnad-test-pw")
        made, _ = self.admit_it(self.ready_business())
        self.assertEqual(made["member"].user.username, "dana-2")

    def test_it_sends_the_setup_link(self):
        made, send = self.admit_it(self.ready_business())
        self.assertTrue(made["mailed"])

        bodies = [c.kwargs["body"] for c in send.call_args_list]
        setup = [b for b in bodies if "/setup/" in b]
        self.assertEqual(len(setup), 1, "expected exactly one setup link")
        self.assertIn("works once and expires in seven days", setup[0])

    def test_the_link_actually_works(self):
        """Guard the guard. A mail containing a URL proves nothing about
        whether that URL resolves to this member."""
        import re

        from site_app.services_setup import resolve_setup_link

        made, send = self.admit_it(self.ready_business())
        body = next(c.kwargs["body"] for c in send.call_args_list
                    if "/setup/" in c.kwargs["body"])
        token = re.search(r"/setup/([^/\s]+)/", body).group(1)

        _link, member = resolve_setup_link(token)
        self.assertEqual(member.pk, made["member"].pk)

    def test_the_application_records_the_organization_it_created(self):
        made, _ = self.admit_it(self.ready_business())
        fresh = Application.objects.get(pk=made["member"].organization.applications.first().pk)
        self.assertEqual(fresh.organization, made["organization"])
        self.assertTrue(fresh.admitted)

    def test_admitting_twice_does_not_create_a_second_organization(self):
        from site_app.models import Organization
        from site_app.services_applications import AdmissionProblem

        application = self.ready_business()
        self.admit_it(application)
        with self.assertRaises(AdmissionProblem):
            self.admit_it(Application.objects.get(pk=application.pk))
        self.assertEqual(
            Organization.objects.filter(name="Alderman Electric LLC").count(), 1)

    def test_nothing_is_created_for_an_application_that_is_not_ready(self):
        """Not ready now means one thing: they have not agreed to the policy.
        The property that matters is unchanged — a refused admission builds
        no organization, no member and no setup link."""
        from site_app.models import Organization
        from site_app.services_applications import admit_to_network

        application = submit(
            kind=Application.BUSINESS, legal_name="Alderman Electric LLC",
            contact_name="Dana", email="dana@example.test",
            statement="We wire things.", agreed=False)

        with self.assertRaises(NotReady):
            admit_to_network(application=application, user=self.reviewer)
        self.assertEqual(Organization.objects.count(), 0)


    def test_an_individual_must_be_admitted_into_an_existing_organization(self):
        """A person admitted into nothing can see nothing: every row is
        scoped to a tenant, so a memberless login is a blank screen."""
        from site_app.services_applications import AdmissionProblem

        application = submit(
            kind=Application.INDIVIDUAL, legal_name="Ola Nilsen",
            contact_name="Ola Nilsen", email="ola@example.test",
            statement="A truck.", agreed=True)
        record_screening(
            application=application, user=self.reviewer, source="A registry",
            searched_name="Ola Nilsen", searched_on=date.today(), clear=True)

        with self.assertRaises(AdmissionProblem) as caught:
            self.admit_it(Application.objects.get(pk=application.pk))
        self.assertIn("--into", str(caught.exception))

    def test_an_individual_joins_the_named_organization_without_privilege(self):
        from site_app.models import Organization
        from site_app.tenancy import tenant_context

        host = Organization.objects.create(slug="rivertown", name="Rivertown")
        application = submit(
            kind=Application.INDIVIDUAL, legal_name="Ola Nilsen",
            contact_name="Ola Nilsen", email="ola@example.test",
            statement="A truck.", agreed=True)
        record_screening(
            application=application, user=self.reviewer, source="A registry",
            searched_name="Ola Nilsen", searched_on=date.today(), clear=True)

        made, _ = self.admit_it(Application.objects.get(pk=application.pk),
                                into=host)
        with tenant_context(host):
            self.assertEqual(made["member"].organization, host)
            self.assertFalse(made["member"].is_organizer)

    def test_a_chapter_gets_a_region_and_no_login(self):
        """No account on purpose: there is no chapter screen to sign into, and
        issuing a credential for a door that does not exist teaches somebody
        their password does not work."""
        from django.contrib.auth.models import User
        from site_app.models import Region

        application = submit(
            kind=Application.CHAPTER, legal_name="Midlands South Carolina",
            contact_name="Sam Reed", email="sam@example.test",
            statement="We want to start one here.", agreed=True)

        made, send = self.admit_it(Application.objects.get(pk=application.pk))

        self.assertIsNotNone(Region.objects.filter(slug="midlands-south-carolina").first())
        self.assertIsNone(made["member"])
        self.assertFalse(made["mailed"])
        self.assertFalse(User.objects.filter(username="sam").exists())
        self.assertEqual(
            [c for c in send.call_args_list if "/setup/" in c.kwargs["body"]], [])


class TheCommandIsWhatAPersonRuns(ApplicationBase):
    def run_decide(self, application, *args):
        from io import StringIO
        from unittest.mock import patch

        from django.core.management import call_command

        out = StringIO()
        with patch("kjerne_platform.email.send", return_value=1) as send:
            call_command("decide_application", str(application.id),
                         "--by", "reviewer", *args, stdout=out)
        return out.getvalue(), send

    def test_admitting_end_to_end_from_the_command_line(self):
        from site_app.models import Organization

        application = self.a_business()
        self.verify_all(application)
        output, send = self.run_decide(application, "--admit")

        self.assertIn("organization:", output)
        self.assertIn("setup link:    sent", output)
        self.assertTrue(Organization.objects.filter(
            slug="alderman-electric-llc").exists())
        self.assertEqual(
            len([c for c in send.call_args_list if "/setup/" in c.kwargs["body"]]), 1)

    def test_an_admitted_applicant_is_not_told_somebody_will_be_in_touch(self):
        """That sentence was true until the setup link was wired. Now the
        account exists and the link is already in their inbox, so a second
        letter promising to set one up contradicts the first."""
        application = self.a_business()
        self.verify_all(application)
        _output, send = self.run_decide(application, "--admit")

        bodies = " ".join(c.kwargs["body"] for c in send.call_args_list)
        self.assertNotIn("will be in touch", bodies)
        self.assertIn("/setup/", bodies)

    def test_the_command_refuses_and_names_what_is_missing(self):
        """One reason left to name, and the command still names it rather
        than failing with a stack trace at somebody."""
        application = submit(
            kind=Application.BUSINESS, legal_name="Alderman Electric LLC",
            contact_name="Dana", email="dana@example.test",
            statement="We wire things.", agreed=False)

        from django.core.management.base import CommandError

        with self.assertRaises(CommandError) as caught:
            self.run_decide(application, "--admit")
        self.assertIn("policy has not been agreed", str(caught.exception))


    def test_declining_from_the_command_line_tells_the_applicant(self):
        application = self.a_business()
        output, send = self.run_decide(application, "--decline",
                                       "--note", "Out of area.")
        self.assertIn("Declined", output)
        self.assertIn("not been taken forward", send.call_args.kwargs["body"])

    def test_a_chapter_admitted_from_the_command_line_gets_no_login(self):
        application = submit(
            kind=Application.CHAPTER, legal_name="Midlands South Carolina",
            contact_name="Sam Reed", email="sam@example.test",
            statement="Starting one here.", agreed=True)
        output, send = self.run_decide(application, "--admit")

        self.assertIn("chapter:", output)
        self.assertIn("No login was created", output)
        # It DOES get the acceptance letter, because no setup mail carried it.
        self.assertIn("accepted", " ".join(
            c.kwargs["body"] for c in send.call_args_list))
