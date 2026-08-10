"""The virtual warehouse: what it records, and the two things it must not.

The bottleneck in mutual aid is materials, not willing hands, and this is the
only part of the system that moves that. It works because of what it refuses.

NO CUSTODY. Goods stay where their holder keeps them. No title means no storage
liability, no insurance obligation, no unrelated-business exposure, and the
platform stays a directory — the same posture that keeps hours a record rather
than a currency.

NO VALUATION. A manifest proves material MOVED. What it was worth is between
the donor, their advisor and the IRS. A dollar figure here would be an
appraisal of donated property produced by a platform about a donor, which is
the single most dangerous artifact this system could emit.

And one operational rule with the same shape as a bug found earlier tonight:
staleness must never render as availability. Someone drives forty miles on a
quantity nobody has looked at in a month.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from site_app.models import (Manifest, Member, Organization, StockLine,
                             Warehouse)
from site_app.tenancy import bypass_rls, tenant_context

from .helpers import SignedIn


class WarehouseBase(SignedIn, TestCase):
    def setUp(self):
        self.alpha = Organization.objects.create(slug="alpha", name="Alpha Mutual Aid")
        self.beta = Organization.objects.create(slug="beta", name="Beta Mutual Aid")

        self.ada_user = User.objects.create_user(
            "ada", email="ada@example.test", password="dugnad-test-pw")
        self.ola_user = User.objects.create_user(
            "ola", email="ola@example.test", password="dugnad-test-pw")
        self.bo_user = User.objects.create_user(
            "bo", email="bo@example.test", password="dugnad-test-pw")

        with tenant_context(self.alpha):
            self.ada = Member.objects.create(
                organization=self.alpha, display_name="Ada", user=self.ada_user)
            self.ola = Member.objects.create(
                organization=self.alpha, display_name="Ola", user=self.ola_user)
            self.barn = Warehouse.objects.create(
                organization=self.alpha, holder=self.ada,
                name="Wolters Farm, north barn",
                address="Second barn, gate code 4412")
            self.lumber = StockLine.objects.create(
                organization=self.alpha, warehouse=self.barn,
                description="Reclaimed oak, mostly 2x8",
                quantity=Decimal("200.00"), unit="board-feet",
                confirmed_at=timezone.now(), confirmed_by=self.ada)

        with tenant_context(self.beta):
            self.bo = Member.objects.create(
                organization=self.beta, display_name="Bo", user=self.bo_user)

    def age(self, line, days):
        """Backdate a confirmation. Freshness is the whole point of these rows."""
        with tenant_context(self.alpha):
            StockLine.objects.filter(pk=line.pk).update(
                confirmed_at=timezone.now() - timedelta(days=days))
            return StockLine.objects.get(pk=line.pk)


class NothingIsEverPriced(WarehouseBase):
    """The refusal that makes this safe to run at all."""

    def test_no_material_model_carries_a_value(self):
        names = set()
        for model in (Warehouse, StockLine, Manifest):
            names |= {f.name for f in model._meta.get_fields()}

        for forbidden in ("value", "price", "cost", "worth", "amount",
                          "appraisal", "appraised_value", "fair_market_value",
                          "fmv", "retail", "msrp", "estimate", "estimated_value"):
            self.assertNotIn(forbidden, names)

    def test_no_material_model_links_to_the_hours_ledger(self):
        """"200 board-feet became 40 hours" is an exchange rate whether it is
        written as a number or as a foreign key."""
        for model in (Warehouse, StockLine, Manifest):
            for f in model._meta.get_fields():
                related = getattr(f, "related_model", None)
                self.assertNotEqual(
                    getattr(related, "__name__", ""), "Contribution",
                    f"{model.__name__}.{f.name} links material to hours")

    def test_the_stock_form_offers_nowhere_to_put_a_figure(self):
        from site_app.forms import StockLineForm

        self.assertEqual(set(StockLineForm().fields),
                         {"description", "quantity", "unit"})

    def test_the_manifest_page_states_no_value(self):
        with tenant_context(self.alpha):
            doc = Manifest.objects.create(
                organization=self.alpha, stock_line=self.lumber,
                quantity=Decimal("50.00"), destination="Habitat build, Pickens",
                sent_by=self.ada)

        self.sign_in(self.ada_user)
        body = self.client.get(f"/manifest/{doc.id}/").content.decode()

        self.assertIn("50.00", body)          # what moved
        self.assertIn("board-feet", body)
        self.assertNotIn("$", body)           # never what it was worth

    def test_the_policy_check_catches_a_value_field(self):
        """The manifest's own check, proved rather than trusted."""
        from unittest.mock import patch

        from policy import checks

        real = checks._all_fields

        def with_a_price(model):
            fields = list(real(model))
            if model.__name__ == "StockLine":
                fields.append(type("F", (), {"name": "estimated_value"})())
            return fields

        with patch.object(checks, "_all_fields", with_a_price):
            result = checks.no_material_valuation()

        self.assertEqual(result.status, checks.BREACHED)
        self.assertTrue(any("estimated_value" in e for e in result.evidence))


class StalenessNeverReadsAsAvailability(WarehouseBase):
    """Somebody drives forty miles on these numbers."""

    def test_freshness_is_words_rather_than_a_date_to_do_arithmetic_on(self):
        cases = {0: "confirmed today", 1: "confirmed yesterday",
                 5: "confirmed 5 days ago", 30: "not confirmed in 4 weeks",
                 200: "not confirmed in months"}
        for days, expected in cases.items():
            self.assertEqual(self.age(self.lumber, days).freshness, expected,
                             msg=f"{days} days")

    def test_a_month_old_confirmation_is_marked_stale(self):
        self.assertFalse(self.age(self.lumber, 2).stale)
        self.assertTrue(self.age(self.lumber, 30).stale)

    def test_stale_stock_is_shown_rather_than_hidden(self):
        """It may still be there. Dropping it silently would be worse than
        showing it late — the same reasoning as expired needs on the board."""
        self.age(self.lumber, 90)
        self.sign_in(self.ola_user)
        body = self.client.get("/warehouse/").content.decode()

        self.assertIn("Reclaimed oak", body)
        self.assertIn("not confirmed in months", body)

    def test_every_page_showing_a_quantity_also_shows_its_age(self):
        """The rule, asserted on each surface rather than trusted once."""
        self.age(self.lumber, 30)
        self.sign_in(self.ada_user)

        for url in ("/warehouse/", f"/warehouse/{self.barn.id}/",
                    f"/warehouse/line/{self.lumber.id}/send/"):
            body = self.client.get(url).content.decode()
            self.assertIn("board-feet", body, url)
            self.assertIn("not confirmed in", body, url)

    def test_sending_material_does_not_refresh_the_clock(self):
        """The sender knows what they sent; they have not re-counted what is
        left. Letting a shipment reset this would make the shelf look freshly
        checked because something left it."""
        from site_app.services_warehouse import send_material

        old = self.age(self.lumber, 40)
        before = old.confirmed_at

        with tenant_context(self.alpha):
            send_material(line=old, quantity=Decimal("50.00"),
                          destination="Somewhere", member=self.ada)
            old.refresh_from_db()

        self.assertEqual(old.confirmed_at, before)
        self.assertTrue(old.stale)
        self.assertEqual(old.quantity, Decimal("150.00"))

    def test_only_the_holder_can_confirm_what_is_there(self):
        """Anyone else asserting what is in somebody's barn is guessing."""
        self.sign_in(self.ola_user)
        response = self.client.post(
            f"/warehouse/line/{self.lumber.id}/confirm/", {"quantity": "999"})

        self.assertEqual(response.status_code, 403)
        with tenant_context(self.alpha):
            self.lumber.refresh_from_db()
        self.assertEqual(self.lumber.quantity, Decimal("200.00"))

    def test_confirming_moves_the_clock_and_the_quantity(self):
        from site_app.services_warehouse import confirm_line

        old = self.age(self.lumber, 40)
        with tenant_context(self.alpha):
            confirm_line(line=old, member=self.ada, quantity="120")
            old.refresh_from_db()

        self.assertFalse(old.stale)
        self.assertEqual(old.quantity, Decimal("120.00"))


class MaterialMovingOut(WarehouseBase):
    def test_sending_reduces_what_is_recorded(self):
        from site_app.services_warehouse import send_material

        with tenant_context(self.alpha):
            send_material(line=self.lumber, quantity=Decimal("80.00"),
                          destination="Habitat build", member=self.ola)
            self.lumber.refresh_from_db()
        self.assertEqual(self.lumber.quantity, Decimal("120.00"))

    def test_you_cannot_send_more_than_is_recorded(self):
        from site_app.services_warehouse import send_material

        with tenant_context(self.alpha):
            with self.assertRaises(ValueError):
                send_material(line=self.lumber, quantity=Decimal("500.00"),
                              destination="Nowhere", member=self.ola)
            self.lumber.refresh_from_db()
        self.assertEqual(self.lumber.quantity, Decimal("200.00"))

    def test_a_line_that_empties_stops_being_available(self):
        from site_app.services_warehouse import send_material

        with tenant_context(self.alpha):
            send_material(line=self.lumber, quantity=Decimal("200.00"),
                          destination="All of it", member=self.ola)
            self.lumber.refresh_from_db()
        self.assertFalse(self.lumber.available)

    def test_the_destination_is_free_text_not_a_member(self):
        """Material very often goes to somebody outside this organization,
        which is the normal case rather than an exception to model around."""
        field = Manifest._meta.get_field("destination")
        self.assertEqual(field.get_internal_type(), "TextField")


class SigningForIt(WarehouseBase):
    """The receiver is standing in a yard with a phone and no account."""

    def setUp(self):
        super().setUp()
        with tenant_context(self.alpha):
            self.doc = Manifest.objects.create(
                organization=self.alpha, stock_line=self.lumber,
                quantity=Decimal("50.00"), destination="Habitat build, Pickens",
                sent_by=self.ada)
        self.minted = []

    def tearDown(self):
        if not self.minted:
            return
        from kjerne_platform.db import get_conn
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM work_action_token WHERE token = ANY(%s)",
                        (self.minted,))
            conn.commit()

    def mint(self):
        from kjerne_platform.work import port as work_port
        from kjerne_platform.work import tokens

        token = tokens.issue(
            work_port.open("work.toml"), verb="confirm-receipt",
            payload={"manifest": str(self.doc.id)}, tenant=self.alpha.id,
            recipient="yard@example.test")
        self.minted.append(token)
        return token

    def test_a_signed_out_receiver_can_sign_for_it(self):
        token = self.mint()
        response = self.client.get(f"/act/{token}/")

        self.assertEqual(response.status_code, 200)
        with tenant_context(self.alpha):
            self.doc.refresh_from_db()
        self.assertTrue(self.doc.received)

    def test_receiving_twice_is_a_no_op_rather_than_an_error(self):
        """A QR gets scanned twice, by two people, on a loading dock. An error
        message on a phone in a yard helps nobody."""
        from site_app.services_warehouse import receive_material

        with tenant_context(self.alpha):
            first = receive_material(manifest=self.doc, note="Ola signed")
            stamp = first.received_at
            again = receive_material(manifest=self.doc, note="somebody else")

        self.assertEqual(again.received_at, stamp)
        self.assertEqual(again.received_note, "Ola signed")

    def test_the_manifest_carries_a_scannable_code_until_it_is_received(self):
        self.sign_in(self.ada_user)
        body = self.client.get(f"/manifest/{self.doc.id}/").content.decode()
        self.assertIn("<svg", body)

        with tenant_context(self.alpha):
            from site_app.services_warehouse import receive_material
            receive_material(manifest=self.doc, note="Signed")

        after = self.client.get(f"/manifest/{self.doc.id}/").content.decode()
        self.assertIn("Signed for", after)

    def test_the_verb_is_reachable_by_token_and_the_dangerous_ones_are_not(self):
        from kjerne_platform.work import port as work_port

        settings = work_port.open("work.toml").settings.tokens
        self.assertTrue(settings.permits("confirm-receipt"))
        self.assertFalse(settings.permits("record-entry"))
        self.assertFalse(settings.permits("close-item"))


class TheWarehouseIsTenantScoped(WarehouseBase):
    def test_another_organization_sees_no_stock(self):
        with tenant_context(self.beta):
            self.assertEqual(StockLine.objects.count(), 0)
            self.assertEqual(Warehouse.objects.count(), 0)

    def test_the_rows_are_really_there_and_rls_is_what_hides_them(self):
        with bypass_rls():
            self.assertEqual(StockLine.objects.filter(pk=self.lumber.pk).count(), 1)

    def test_a_manifest_is_not_reachable_from_another_organization(self):
        with tenant_context(self.alpha):
            doc = Manifest.objects.create(
                organization=self.alpha, stock_line=self.lumber,
                quantity=Decimal("10.00"), destination="x", sent_by=self.ada)

        self.sign_in(self.bo_user)
        self.assertEqual(self.client.get(f"/manifest/{doc.id}/").status_code, 404)
