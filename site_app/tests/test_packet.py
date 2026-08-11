"""The impact packet.

This is the one document that leaves the organization and goes to somebody who
gave something. So the tests that matter are about what it refuses to say: no
value, no price, no total of anybody's hours, and an explicit statement that it
cannot substantiate a deduction.

The second half is access. A published packet is readable by a stranger with
the link, which is the point -- but nothing unpublished may be, and a
photograph must not be fetchable just because somebody knows its id.
"""

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
        with tenant_context(self.org):
            return add_photo(project=self.project, member=self.member,
                             upload=an_image(), caption="The put-in, at eight.")

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
                    an_image().read(), content_type="image/png"))
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
