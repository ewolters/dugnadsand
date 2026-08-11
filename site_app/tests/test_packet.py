"""The impact packet.

This is the one document that leaves the organization and goes to somebody who
gave something. So the tests that matter are about what it refuses to say: no
value, no price, no total of anybody's hours, and an explicit statement that it
cannot substantiate a deduction.

The second half is access. A published packet is readable by a stranger with
the link, which is the point -- but nothing unpublished may be, and a
photograph must not be fetchable just because somebody knows its id.
"""

from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from site_app.models import (Measure, Member, Organization, Packet, Photo,
                             Project)
from site_app.services_packet import (UnitRefused, add_photo, build_packet,
                                      check_unit, publish_packet,
                                      record_measure, withdraw_packet)
from site_app.tenancy import set_tenant, tenant_context

from .helpers import SignedIn


def an_image():
    """A real PNG, because the validator re-decodes the content."""
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (8, 8), (74, 103, 65)).save(buffer, format="PNG")
    return SimpleUploadedFile("river.png", buffer.getvalue(),
                              content_type="image/png")


class PacketBase(SignedIn, TestCase):
    def setUp(self):
        self.org = Organization.objects.create(slug="alpha", name="Alpha Mutual Aid")
        self.user = User.objects.create_user("ada", password="dugnad-test-pw")
        with tenant_context(self.org):
            self.member = Member.objects.create(
                organization=self.org, display_name="Ada", user=self.user)
            self.project = Project.objects.create(
                organization=self.org, started_by=self.member,
                name="Reedy River cleanup", description="Waders and a skip.")
        set_tenant(None)

    def tearDown(self):
        set_tenant(None)

    def a_packet(self, publish=False):
        with tenant_context(self.org):
            record_measure(project=self.project, member=self.member,
                           label="Debris removed", quantity=Decimal("3.20"),
                           unit="tons")
            packet = build_packet(
                project=self.project, member=self.member,
                title="What the river looks like now",
                summary="Sixty people, one Saturday.",
                acknowledgements="Swamp Rabbit brought lunch.")
            if publish:
                publish_packet(packet=packet, member=self.member)
        return packet


class AMeasureIsNotATotal(PacketBase):
    """The distinction that lets this model exist at all.

    A per-project total of hours looks safe because it describes work rather
    than a person -- but a project with one contributor IS that contributor's
    total, and no-aggregate-display exists to stop that number existing. A
    measure describes the outcome instead.
    """

    def test_money_is_refused(self):
        for unit in ("dollars", "USD", "$", "value", "retail price", "cents"):
            with self.assertRaises(UnitRefused, msg=unit):
                check_unit(unit)

    def test_hours_are_refused(self):
        for unit in ("hours", "hrs", "man-hours", "volunteer hours",
                     "person-hours", "shifts", "workdays"):
            with self.assertRaises(UnitRefused, msg=unit):
                check_unit(unit)

    def test_what_the_work_achieved_is_allowed(self):
        for unit in ("tons", "metres", "houses", "bags", "miles", "trees",
                     "days"):
            self.assertEqual(check_unit(unit), unit)

    def test_the_refusal_reaches_the_service_not_just_the_form(self):
        """The form is one way in, not the rule."""
        with tenant_context(self.org):
            with self.assertRaises(UnitRefused):
                record_measure(project=self.project, member=self.member,
                               label="Value of donations",
                               quantity=Decimal("2400.00"), unit="dollars")
            self.assertEqual(Measure.objects.count(), 0)

    def test_nothing_computes_a_measure_from_the_ledger(self):
        """A measure is typed by a person. If it were derived from
        contributions it would be the aggregate wearing a different name."""
        import inspect

        from site_app import services_packet

        source = inspect.getsource(services_packet)
        for forbidden in ("Contribution", "aggregate(", "Sum("):
            self.assertNotIn(forbidden, source, forbidden)

    def test_no_model_here_carries_a_value(self):
        for model in (Measure, Packet, Photo):
            names = {f.name for f in model._meta.get_fields()}
            for forbidden in ("value", "price", "cost", "amount", "worth",
                              "hours", "total"):
                self.assertNotIn(forbidden, names,
                                 f"{model.__name__} grew {forbidden}")


class TheDocumentRefusesToBeAReceipt(PacketBase):
    def test_it_says_it_is_not_a_receipt_or_a_valuation(self):
        import re

        packet = self.a_packet(publish=True)
        body = re.sub(r"\s+", " ",
                      self.client.get(f"/packet/{packet.token}/").content.decode())
        self.assertIn("not a receipt, and it is not a valuation", body)
        self.assertIn("cannot serve as substantiation for a tax deduction", body)

    def test_it_carries_no_currency_anywhere(self):
        packet = self.a_packet(publish=True)
        body = self.client.get(f"/packet/{packet.token}/").content.decode()
        for symbol in ("$", "USD", "dollar"):
            self.assertNotIn(symbol, body, symbol)

    def test_it_reports_the_outcome(self):
        packet = self.a_packet(publish=True)
        body = self.client.get(f"/packet/{packet.token}/").content.decode()
        self.assertIn("Debris removed", body)
        self.assertIn("3.20", body)
        self.assertIn("tons", body)

    def test_the_thanks_are_prose_somebody_wrote(self):
        """Not a generated list. Generating it would rank people by what they
        gave, which is the score this system exists without."""
        packet = self.a_packet(publish=True)
        body = self.client.get(f"/packet/{packet.token}/").content.decode()
        self.assertIn("Swamp Rabbit brought lunch.", body)


class WhoCanReadIt(PacketBase):
    def test_a_stranger_with_the_link_can(self):
        """The whole point: whoever this was sent to has no account and should
        not need one."""
        packet = self.a_packet(publish=True)
        self.assertEqual(
            self.client.get(f"/packet/{packet.token}/").status_code, 200)

    def test_an_unpublished_packet_has_no_link_at_all(self):
        packet = self.a_packet()
        self.assertEqual(packet.token, "")
        self.assertFalse(packet.published)

    def test_a_wrong_token_is_refused(self):
        self.a_packet(publish=True)
        self.assertEqual(self.client.get("/packet/not-a-real-token/").status_code, 404)

    def test_an_empty_token_cannot_match_an_unpublished_packet(self):
        """The bug this guards: unpublished packets store token="", so a
        lookup that did not exclude the empty string would hand back the first
        unpublished packet in the table to anybody who asked for one."""
        self.a_packet()
        for attempt in ("", " ", "%20"):
            self.assertNotEqual(
                self.client.get(f"/packet/{attempt}/").status_code, 200, attempt)

    def test_withdrawing_kills_the_link_for_good(self):
        packet = self.a_packet(publish=True)
        first = packet.token

        with tenant_context(self.org):
            withdraw_packet(packet)
        self.assertEqual(self.client.get(f"/packet/{first}/").status_code, 404)

        with tenant_context(self.org):
            publish_packet(packet=packet, member=self.member)
        self.assertNotEqual(packet.token, first,
                            "re-publishing revived the old link")
        self.assertEqual(self.client.get(f"/packet/{first}/").status_code, 404)

    def test_publishing_twice_keeps_the_same_link(self):
        """It has been sent to people. Changing it silently would break every
        copy of it."""
        packet = self.a_packet(publish=True)
        first = packet.token
        with tenant_context(self.org):
            publish_packet(packet=packet, member=self.member)
        self.assertEqual(packet.token, first)


class Photographs(PacketBase):
    def add_one(self):
        """depicts_people=False on purpose. These tests are about who may
        FETCH a file; the consent gate has its own class, and leaving it
        engaged here would make every one of them fail for the wrong
        reason."""
        with tenant_context(self.org):
            return add_photo(project=self.project, member=self.member,
                             upload=an_image(), caption="The put-in, at eight.",
                             depicts_people=False)

    def test_a_photo_is_served_once_the_packet_is_published(self):
        photo = self.add_one()
        self.a_packet(publish=True)
        response = self.client.get(f"/photo/{photo.id}/")
        self.assertEqual(response.status_code, 200)

    def test_it_is_not_served_while_the_packet_is_unpublished(self):
        """A file under a guessable URL is public from the moment it is
        written. /media/ is routed nowhere and this view is the access rule."""
        photo = self.add_one()
        self.a_packet()
        self.assertEqual(self.client.get(f"/photo/{photo.id}/").status_code, 404)

    def test_a_member_of_that_organization_sees_it_unpublished(self):
        photo = self.add_one()
        self.a_packet()
        self.sign_in(self.user)
        self.assertEqual(self.client.get(f"/photo/{photo.id}/").status_code, 200)

    def test_a_member_of_another_organization_does_not(self):
        photo = self.add_one()
        self.a_packet()

        beta = Organization.objects.create(slug="beta", name="Beta")
        other = User.objects.create_user("bo", password="dugnad-test-pw")
        with tenant_context(beta):
            Member.objects.create(organization=beta, display_name="Bo", user=other)
        set_tenant(None)

        self.sign_in(other)
        self.assertEqual(self.client.get(f"/photo/{photo.id}/").status_code, 404)

    def test_withdrawing_the_packet_closes_the_photo_again(self):
        photo = self.add_one()
        packet = self.a_packet(publish=True)
        self.assertEqual(self.client.get(f"/photo/{photo.id}/").status_code, 200)

        with tenant_context(self.org):
            withdraw_packet(packet)
        self.assertEqual(self.client.get(f"/photo/{photo.id}/").status_code, 404)

    def test_something_that_is_not_an_image_is_refused(self):
        with tenant_context(self.org):
            with self.assertRaises(ValueError):
                add_photo(project=self.project, member=self.member,
                          upload=SimpleUploadedFile(
                              "river.png", b"not a png at all",
                              content_type="image/png"))

    def test_the_original_filename_is_discarded(self):
        """It is somebody's phone's idea of a name, frequently carrying a date
        or a place, and it is attacker-controlled."""
        with tenant_context(self.org):
            photo = add_photo(
                project=self.project, member=self.member,
                upload=SimpleUploadedFile(
                    "2026-08-11 Greenville Dana's house.png",
                    an_image().read(), content_type="image/png"),
                depicts_people=False)
        self.assertNotIn("Greenville", photo.image.name)
        self.assertNotIn("Dana", photo.image.name)
        self.assertTrue(photo.image.name.startswith("packets/"))


class TheBuildPage(PacketBase):
    def test_a_member_can_reach_it(self):
        self.sign_in(self.user)
        self.assertEqual(
            self.client.get(f"/projects/{self.project.id}/packet/").status_code, 200)

    def test_a_signed_out_visitor_cannot(self):
        response = self.client.get(f"/projects/{self.project.id}/packet/")
        self.assertNotEqual(response.status_code, 200)

    def test_a_money_unit_is_refused_on_the_page_with_a_reason(self):
        self.sign_in(self.user)
        response = self.client.post(f"/projects/{self.project.id}/packet/", {
            "what": "measure", "label": "Donations", "quantity": "2400",
            "unit": "dollars", "note": ""})
        self.assertEqual(response.status_code, 200)
        self.assertIn("not counted in money", response.content.decode())
        with tenant_context(self.org):
            self.assertEqual(Measure.objects.count(), 0)

    def test_publishing_from_the_page_mints_a_link(self):
        self.a_packet()
        self.sign_in(self.user)
        self.client.post(f"/projects/{self.project.id}/packet/publish/")

        with tenant_context(self.org):
            self.assertTrue(Packet.objects.get(project=self.project).published)


class ConsentGatesPublication(PacketBase):
    """A face goes out only when somebody recorded that its owner agreed."""

    def a_photo(self, depicts_people=True):
        from site_app.services_packet import add_photo

        with tenant_context(self.org):
            return add_photo(project=self.project, member=self.member,
                             upload=an_image(), caption="At the put-in",
                             depicts_people=depicts_people)

    def test_a_photo_of_people_with_nobody_named_blocks(self):
        from site_app.services_packet import ConsentOutstanding

        self.a_photo()
        packet = self.a_packet()
        with tenant_context(self.org):
            with self.assertRaises(ConsentOutstanding) as caught:
                publish_packet(packet=packet, member=self.member)
        self.assertIn("nobody is named", str(caught.exception))

    def test_a_photo_declared_to_show_no_people_does_not(self):
        self.a_photo(depicts_people=False)
        packet = self.a_packet()
        with tenant_context(self.org):
            publish_packet(packet=packet, member=self.member)
        self.assertTrue(packet.published)

    def test_naming_somebody_who_has_not_agreed_still_blocks(self):
        from site_app.services_packet import ConsentOutstanding, expect_consent

        photo = self.a_photo()
        packet = self.a_packet()
        with tenant_context(self.org):
            expect_consent(photo=photo, member=self.member, person="Ola Nilsen")
            with self.assertRaises(ConsentOutstanding) as caught:
                publish_packet(packet=packet, member=self.member)
        self.assertIn("Ola Nilsen has not agreed yet", str(caught.exception))

    def test_recording_agreement_releases_it(self):
        from site_app.services_packet import record_consent

        photo = self.a_photo()
        packet = self.a_packet()
        with tenant_context(self.org):
            record_consent(photo=photo, member=self.member, person="Ola Nilsen",
                           given_on=date.today(), how="in person")
            publish_packet(packet=packet, member=self.member)
        self.assertTrue(packet.published)

    def test_a_withdrawal_blocks_again(self):
        """The property that makes this consent rather than a checkbox."""
        from site_app.services_packet import (ConsentOutstanding,
                                              record_consent, withdraw_consent)

        photo = self.a_photo()
        packet = self.a_packet()
        with tenant_context(self.org):
            record_consent(photo=photo, member=self.member, person="Ola Nilsen",
                           given_on=date.today(), how="in person")
            publish_packet(packet=packet, member=self.member)

            withdraw_consent(photo=photo, member=self.member,
                             person="Ola Nilsen", withdrawn_on=date.today())
            with self.assertRaises(ConsentOutstanding) as caught:
                publish_packet(packet=packet, member=self.member)
        self.assertIn("withdrawn", str(caught.exception))

    def test_the_gate_is_in_the_service_not_the_view(self):
        """So nothing publishes faces by going round the screen."""
        import inspect

        from site_app import services_packet

        source = inspect.getsource(services_packet.publish_packet)
        self.assertIn("consent_blockers", source)

    def test_two_spellings_of_one_name_do_not_become_two_people(self):
        """State is keyed on the digest, which normalises case and spacing."""
        from site_app.services_packet import (consent_state, expect_consent,
                                              record_consent)

        photo = self.a_photo()
        with tenant_context(self.org):
            expect_consent(photo=photo, member=self.member, person="Ola Nilsen")
            record_consent(photo=photo, member=self.member,
                           person="  ola nilsen ", given_on=date.today())
            state = consent_state(photo)
        self.assertEqual(len(state), 1)
        self.assertTrue(state[0].given)


class TheConsentChainIsTamperEvident(PacketBase):
    """Consent is the record most worth altering afterwards.

    Somebody who published a photograph they should not have has every motive
    to make a consent appear, or a withdrawal vanish.
    """

    def setUp(self):
        super().setUp()
        from site_app.services_packet import (add_photo, expect_consent,
                                              record_consent)

        with tenant_context(self.org):
            self.photo = add_photo(project=self.project, member=self.member,
                                   upload=an_image())
            expect_consent(photo=self.photo, member=self.member, person="Ola")
            record_consent(photo=self.photo, member=self.member, person="Ola",
                           given_on=date.today(), how="in person")

    def verify(self):
        from site_app.services_packet import verify_consents

        with tenant_context(self.org):
            return verify_consents(self.org.id)

    def test_an_untouched_chain_verifies(self):
        self.assertTrue(self.verify().ok)

    def test_it_chains_in_order_from_zero(self):
        from site_app.models import PhotoConsent

        with tenant_context(self.org):
            entries = list(PhotoConsent.objects.order_by("sequence"))
        self.assertEqual([e.sequence for e in entries], [0, 1])
        self.assertEqual(entries[0].previous_hash, "")
        self.assertEqual(entries[1].previous_hash, entries[0].entry_hash)

    def test_rewriting_a_consent_date_breaks_it(self):
        from datetime import timedelta

        from site_app.models import PhotoConsent

        with tenant_context(self.org):
            entry = PhotoConsent.objects.order_by("-sequence").first()
            PhotoConsent.objects.filter(pk=entry.pk).update(
                given_on=date.today() - timedelta(days=400))

        self.assertFalse(self.verify().ok,
                         "a back-dated consent verified clean")

    def test_changing_who_agreed_breaks_it(self):
        from site_app.models import PhotoConsent

        with tenant_context(self.org):
            entry = PhotoConsent.objects.order_by("-sequence").first()
            entry.person = "Somebody Else"
            entry.save(update_fields=["person"])

        self.assertFalse(self.verify().ok,
                         "the name was swapped and the chain still verified")

    def test_deleting_the_last_entry_is_NOT_caught_by_the_chain_alone(self):
        """The known limit, asserted rather than left to be discovered.

        A hash chain detects insertion, edit and deletion from the MIDDLE,
        because every later entry commits to what came before. It cannot
        detect truncation of the END: chop the tip off and what remains is a
        perfectly valid shorter chain.

        That matters here more than it does for hours, because the tip is
        exactly what somebody would remove — the withdrawal that arrived last.
        Closing it needs the tip recorded somewhere the same person cannot
        edit, which the attestation chain does for the manifest and nothing
        yet does for this one.
        """
        from site_app.models import PhotoConsent
        from site_app.services_packet import withdraw_consent

        with tenant_context(self.org):
            withdraw_consent(photo=self.photo, member=self.member,
                             person="Ola", withdrawn_on=date.today())
            PhotoConsent.objects.order_by("-sequence").first().delete()

        report = self.verify()
        self.assertTrue(report.ok,
                        "deleting the TIP is not detectable by the chain alone")

    def test_deleting_an_entry_from_the_middle_breaks_it(self):
        from site_app.models import PhotoConsent
        from site_app.services_packet import withdraw_consent

        with tenant_context(self.org):
            withdraw_consent(photo=self.photo, member=self.member,
                             person="Ola", withdrawn_on=date.today())
            PhotoConsent.objects.filter(sequence=1).delete()

        self.assertFalse(self.verify().ok)

    def test_the_name_is_not_stored_in_the_clear(self):
        from django.db import connection

        from site_app.models import PhotoConsent

        # INSIDE the tenant: the raw cursor is subject to RLS exactly as the
        # ORM is, so a query outside it returns no row at all rather than an
        # unencrypted one — which would have read as a passing test.
        with tenant_context(self.org):
            pk = PhotoConsent.objects.first().pk
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT person FROM site_app_photoconsent WHERE id = %s",
                    [str(pk)])
                stored = cur.fetchone()[0]
        self.assertNotIn("Ola", stored)

    def test_the_chain_payload_carries_a_keyed_digest_not_the_name(self):
        """A bare hash would let somebody with a stolen database confirm a
        guessed name without ever holding the encryption key."""
        import hashlib

        from site_app.services_packet import person_digest

        self.assertNotEqual(person_digest("Ola"),
                            hashlib.sha256(b"ola").hexdigest())
        self.assertEqual(person_digest("Ola"), person_digest(" ola "))
