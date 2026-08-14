"""An officer deciding an application from the chapter screen.

This moved off the command line because a network whose admissions all route
through one laptop is not a network of chapters. What did NOT move is that a
person decides: the gate still refuses while anything is unverified, expired,
unscreened or unagreed, and it still names every reason.

The tests that matter are the ones about who may do it. An officer of one
chapter deciding another chapter's application would be the whole roster
model undone by a URL.
"""

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase

from site_app.models import (Application, Credential, Member, Organization,
                             Region, RegionRole, Screening)
from site_app.services_applications import submit
from site_app.tenancy import set_tenant, tenant_context

from .helpers import SignedIn


class ReviewBase(SignedIn, TestCase):
    def setUp(self):
        self.upstate = Region.objects.create(slug="up", name="Upstate")
        self.midlands = Region.objects.create(slug="mid", name="Midlands")

        self.hannah = User.objects.create_user("hannah", password="dugnad-test-pw")
        RegionRole.objects.create(region=self.upstate, user=self.hannah,
                                  role=RegionRole.LEAD, title="Officer")
        self.stranger = User.objects.create_user("sam", password="dugnad-test-pw")
        RegionRole.objects.create(region=self.midlands, user=self.stranger,
                                  role=RegionRole.LEAD)
        self.nobody = User.objects.create_user("nobody", password="dugnad-test-pw")

        self.application = submit(
            kind=Application.BUSINESS, region=self.upstate,
            legal_name="Alderman Electric LLC", contact_name="Dana Alderman",
            email="dana@example.test", statement="We wire things.", agreed=True,
            credentials={
                "Business license": {"authority": "SC LLR", "reference": "EL-44821",
                                     "expires_on": date.today() + timedelta(days=200)},
                "Certificate of insurance": {"reference": "CGL-9912",
                                             "expires_on": date.today() + timedelta(days=90)},
                "Tax identification number": {"reference": "57-1234567"}})
        set_tenant(None)

    def tearDown(self):
        set_tenant(None)

    def url(self):
        return f"/chapter/application/{self.application.id}/"

    def verify_everything(self):
        for credential in self.application.credentials.all():
            self.client.post(self.url(), {
                "what": "verify", "credential": str(credential.id)})


class WhoMayDecide(ReviewBase):
    def test_an_officer_of_that_chapter_can_open_it(self):
        self.sign_in(self.hannah)
        self.assertEqual(self.client.get(self.url()).status_code, 200)

    def test_an_officer_of_a_DIFFERENT_chapter_cannot(self):
        """The roster model undone by a URL, if this were not checked. The
        permission is by region id, not by "is an officer somewhere"."""
        self.sign_in(self.stranger)
        self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_somebody_with_no_role_cannot(self):
        self.sign_in(self.nobody)
        self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_a_signed_out_visitor_cannot(self):
        self.assertNotEqual(self.client.get(self.url()).status_code, 200)

    def test_a_stranger_cannot_decide_it_by_posting_either(self):
        """Reading is refused above; this is the half that would matter."""
        self.sign_in(self.stranger)
        response = self.client.post(self.url(), {"what": "decline"})
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(Application.objects.get(pk=self.application.pk).admitted)


class WhatAnOfficerSees(ReviewBase):
    def test_the_tax_number_is_shown(self):
        """Withholding it would leave a Verify button nobody could honestly
        press: a credential is checked against the reference on it."""
        self.sign_in(self.hannah)
        self.assertContains(self.client.get(self.url()), "57-1234567")

    def test_it_is_not_shown_on_the_roster(self):
        """The list is a queue. The reference appears on the page somebody
        opened deliberately, and nowhere else."""
        self.sign_in(self.hannah)
        self.assertNotContains(self.client.get("/chapter/"), "57-1234567")

    def test_what_nobody_looked_at_is_named(self):
        """Was "the blockers are named". It is context for a person now,
        not a refusal by the system, and it still has to be on the page."""
        self.sign_in(self.hannah)
        self.assertContains(self.client.get(self.url()),
                            "Business license — nobody has looked at this")


class Verifying(ReviewBase):
    def test_it_records_who_looked(self):
        self.sign_in(self.hannah)
        credential = self.application.credentials.get(kind="Business license")
        self.client.post(self.url(), {"what": "verify",
                                      "credential": str(credential.id)})

        fresh = Credential.objects.get(pk=credential.pk)
        self.assertEqual(fresh.verified_by, self.hannah)
        self.assertEqual(fresh.verified_on, date.today())

    def test_an_expiry_can_be_corrected_while_verifying(self):
        """The date on the document wins over the date somebody typed in."""
        self.sign_in(self.hannah)
        credential = self.application.credentials.get(kind="Business license")
        corrected = date.today() + timedelta(days=30)
        self.client.post(self.url(), {
            "what": "verify", "credential": str(credential.id),
            "expires": corrected.isoformat()})

        self.assertEqual(Credential.objects.get(pk=credential.pk).expires_on,
                         corrected)

    def test_a_credential_from_another_application_cannot_be_verified(self):
        other = submit(kind=Application.NONPROFIT, region=self.upstate,
                       legal_name="Other Trust", contact_name="Pat",
                       email="pat@example.test", statement="x", agreed=True,
                       credentials={"Tax identification number": {"reference": "1"}})
        theirs = other.credentials.first()

        self.sign_in(self.hannah)
        response = self.client.post(self.url(), {
            "what": "verify", "credential": str(theirs.id)})
        self.assertEqual(response.status_code, 404)


class Screening_(ReviewBase):
    def test_a_search_is_recorded_against_the_officer(self):
        self.sign_in(self.hannah)
        self.client.post(self.url(), {
            "what": "screen", "source": "SC business licence lookup"})

        entry = Screening.objects.get(application=self.application)
        self.assertEqual(entry.searched_by, self.hannah)
        self.assertTrue(entry.clear)

    def test_a_hit_is_recorded_as_needing_a_person(self):
        self.sign_in(self.hannah)
        self.client.post(self.url(), {
            "what": "screen", "source": "A registry", "found": "1"})
        self.assertFalse(Screening.objects.get(application=self.application).clear)

    def test_a_search_with_no_registry_named_is_refused(self):
        self.sign_in(self.hannah)
        response = self.client.post(self.url(), {"what": "screen", "source": " "})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Screening.objects.count(), 0)


class Deciding(ReviewBase):
    def test_admitting_is_permitted_with_nothing_verified(self):
        """Was "refused while anything is outstanding". Verification stopped
        being a gate because recording that we checked a licence is a
        representation to everybody else — see Application.blockers."""
        self.sign_in(self.hannah)
        self.client.post(self.url(), {"what": "admit"}, follow=True)

        application = Application.objects.get(pk=self.application.pk)
        self.assertTrue(application.admitted)
        self.assertEqual(Organization.objects.count(), 1)


    def test_the_button_is_not_disabled_by_an_unchecked_credential(self):
        self.sign_in(self.hannah)
        body = self.client.get(self.url()).content.decode()
        import re as re_

        self.assertIsNone(re_.search(r"<button[^>]*disabled", body))

    def test_but_the_page_says_nobody_checked(self):
        """The information survives the gate being removed, and the page
        says plainly what admission does and does not mean."""
        self.sign_in(self.hannah)
        body = self.client.get(self.url()).content.decode()
        self.assertIn("Nobody has checked", body)
        # Not "not vouching for it" -- the template wraps mid-phrase, and a
        # bare substring across a line break is the assertion that lies.
        self.assertIn("Registering an organization is not", body)


    def test_verifying_everything_then_admitting_builds_the_organization(self):
        from unittest.mock import patch

        self.sign_in(self.hannah)
        self.verify_everything()
        with patch("kjerne_platform.email.send", return_value=1) as send:
            self.client.post(self.url(), {"what": "admit"})

        application = Application.objects.get(pk=self.application.pk)
        self.assertTrue(application.admitted)
        self.assertEqual(application.decided_by, self.hannah)

        organization = Organization.objects.get(slug="alderman-electric-llc")
        self.assertEqual(organization.region, self.upstate)
        self.assertTrue(any("/setup/" in c.kwargs["body"]
                            for c in send.call_args_list))

    def test_declining_tells_the_applicant_without_the_note(self):
        from unittest.mock import patch

        self.sign_in(self.hannah)
        with patch("kjerne_platform.email.send", return_value=1) as send:
            self.client.post(self.url(), {
                "what": "decline", "note": "Could not reach them twice."})

        self.assertFalse(Application.objects.get(pk=self.application.pk).admitted)
        body = send.call_args.kwargs["body"]
        self.assertIn("not been taken forward", body)
        self.assertNotIn("Could not reach", body)

    def test_a_decided_application_offers_no_further_decision(self):
        self.sign_in(self.hannah)
        self.client.post(self.url(), {"what": "decline"})

        body = self.client.get(self.url()).content.decode()
        self.assertIn("Not taken forward", body)
        self.assertNotIn('value="admit"', body)

    def test_an_individual_may_only_join_an_organization_in_this_chapter(self):
        """A picker offering any organization anywhere would let an officer
        place somebody outside their own chapter."""
        elsewhere = Organization.objects.create(
            slug="far", name="Far", region=self.midlands)
        individual = submit(
            kind=Application.INDIVIDUAL, region=self.upstate,
            legal_name="Ola Nilsen", contact_name="Ola Nilsen",
            email="ola@example.test", statement="A truck.", agreed=True)

        self.sign_in(self.hannah)
        response = self.client.post(
            f"/chapter/application/{individual.id}/",
            {"what": "admit", "into": str(elsewhere.id)})
        self.assertEqual(response.status_code, 404)
