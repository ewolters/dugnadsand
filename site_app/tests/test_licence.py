"""Offering skilled work under the licence you hold to do it.

An electrician offering an evening here is offering it as an electrician. The
licence is not suspended because the work is unpaid, and nobody's insurer
cares that the panel was rewired as a favour.

The properties worth holding:

  It appears ONLY where a licence is held. Most members hold none, and a
  standing "I hold no licence" checkbox on every offer of a lift would be the
  system talking about itself instead of getting out of the way.

  IT IS DECLARED, NEVER VERIFIED. The network does not check that the licence
  exists and does not vouch for it — that check was a representation to
  everybody else, and it is the member's claim to make. Expiry does not
  suppress the question either: filtering expired credentials out meant an
  expiry made the system ask for LESS, and the posting went up looking like
  one from somebody who had never held a licence.

  What was agreed is SNAPSHOTTED as text. A licence renewed, corrected or
  lapsed next year must not rewrite what somebody agreed to in March.

  It is not a rank. Nothing sorts, filters or scores by it.
"""

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase

from site_app.models import Application, Credential, Member, Organization, Region
from site_app.services_licence import (LicenceNotAffirmed, held_by, sentence,
                                       snapshot)
from site_app.tenancy import set_tenant, tenant_context

from .helpers import SignedIn


class Fixture(SignedIn, TestCase):
    def setUp(self):
        self.region = Region.objects.create(slug="up", name="Upstate")
        self.sparks = Organization.objects.create(
            slug="alderman", name="Alderman Electric LLC", region=self.region,
            kind=Organization.BUSINESS)
        self.plain = Organization.objects.create(
            slug="plain", name="The Hendersons", region=self.region,
            kind=Organization.HOUSEHOLD)

        self.dana = self.member_for(self.sparks, "dana")
        self.ada = self.member_for(self.plain, "ada")
        set_tenant(None)

    def tearDown(self):
        set_tenant(None)

    def member_for(self, organization, username):
        user = User.objects.create_user(username, password="dugnad-test-pw")
        set_tenant(organization.id, organization.region_id)
        member = Member.objects.create(organization=organization, user=user,
                                       display_name=username.title())
        set_tenant(None)
        return member

    def give_licence(self, organization, kind="Electrical contractor licence",
                     authority="SC LLR", expires=None, verified=True):
        application = Application.objects.create(
            kind=Application.BUSINESS, region=self.region,
            organization=organization, legal_name=organization.name,
            contact_name="Dana", email="dana@example.test",
            statement="We wire things.")
        return Credential.objects.create(
            application=application, kind=kind, authority=authority,
            reference="EL-44821",
            expires_on=expires if expires is not None
            else date.today() + timedelta(days=200),
            verified_on=date.today() if verified else None)


class WhichCredentialsCount(Fixture):
    def test_a_verified_current_licence_counts(self):
        self.give_licence(self.sparks)
        self.assertEqual(held_by(self.sparks),
                         ["Electrical contractor licence (SC LLR)"])

    def test_AN_EXPIRED_ONE_STILL_ASKS(self):
        """Reversed deliberately, and it fixed a live defect.

        Filtering expired credentials out meant no affirmation was asked at
        all, so the posting went up looking exactly like one from somebody
        who had never held a licence. An expiry made the system ask for
        LESS. It now asks the same question either way, and the sentence
        says the licence is current — which is a thing they know and the
        system does not.
        """
        self.give_licence(self.sparks, expires=date.today() - timedelta(days=1))
        self.assertEqual(held_by(self.sparks),
                         ["Electrical contractor licence (SC LLR)"])
        self.assertIn("which is current", sentence(self.sparks))

    def test_one_nobody_verified_still_asks(self):
        """It is their licence and their claim. Gating the question on our
        check turned their statement into our representation, which is the
        one thing this system stopped doing."""
        self.give_licence(self.sparks, verified=False)
        self.assertEqual(held_by(self.sparks),
                         ["Electrical contractor licence (SC LLR)"])

    def test_a_tax_number_is_not_a_licence(self):
        self.give_licence(self.sparks, kind="Tax identification number",
                          authority="IRS")
        self.assertEqual(held_by(self.sparks), [])

    def test_the_reference_number_never_appears(self):
        """reference holds a tax identification number for some
        organizations — the single most sensitive value stored here. It has
        no business on a posting a whole chapter reads."""
        self.give_licence(self.sparks)
        self.assertNotIn("EL-44821", " ".join(held_by(self.sparks)))
        self.assertNotIn("EL-44821", sentence(self.sparks))

    def test_an_organization_holding_nothing_is_asked_nothing(self):
        self.assertIsNone(sentence(self.plain))


class PostingAnOffer(Fixture):
    def test_the_composer_shows_the_tick_to_a_licensed_organization(self):
        self.give_licence(self.sparks)
        self.sign_in(self.dana.user)

        body = self.client.get("/board/new/").content.decode()
        self.assertIn('name="under_licence"', body)
        self.assertIn("Alderman Electric LLC", body)

    def test_the_composer_shows_nothing_to_everybody_else(self):
        self.sign_in(self.ada.user)
        self.assertNotIn('name="under_licence"',
                         self.client.get("/board/new/").content.decode())

    def test_posting_without_ticking_is_refused(self):
        from site_app.models import Posting

        self.give_licence(self.sparks)
        self.sign_in(self.dana.user)
        response = self.client.post("/board/new/", {
            "kind": "offer", "description": "An evening rewiring a panel.",
            "hours_cap": "4"})

        self.assertEqual(response.status_code, 200)
        with tenant_context(self.sparks):
            self.assertEqual(Posting.objects.count(), 0)

    def test_ticking_snapshots_the_licence_onto_the_posting(self):
        from site_app.models import Posting

        self.give_licence(self.sparks)
        self.sign_in(self.dana.user)
        self.client.post("/board/new/", {
            "kind": "offer", "description": "An evening rewiring a panel.",
            "hours_cap": "4", "under_licence": "1"})

        with tenant_context(self.sparks):
            posting = Posting.objects.get()
            self.assertEqual(posting.offered_under,
                             "Electrical contractor licence (SC LLR)")

    def test_a_later_lapse_does_not_rewrite_what_was_agreed(self):
        """The reason it is text and not a foreign key."""
        from site_app.models import Posting

        credential = self.give_licence(self.sparks)
        self.sign_in(self.dana.user)
        self.client.post("/board/new/", {
            "kind": "offer", "description": "An evening.", "hours_cap": "4",
            "under_licence": "1"})

        credential.expires_on = date.today() - timedelta(days=1)
        credential.save(update_fields=["expires_on"])

        with tenant_context(self.sparks):
            self.assertEqual(Posting.objects.get().offered_under,
                             "Electrical contractor licence (SC LLR)")

    def test_an_unlicensed_member_posts_with_no_extra_step(self):
        from site_app.models import Posting

        self.sign_in(self.ada.user)
        self.client.post("/board/new/", {
            "kind": "offer", "description": "A lift, most Saturdays.",
            "hours_cap": ""})

        with tenant_context(self.plain):
            self.assertEqual(Posting.objects.get().offered_under, "")


class PuttingYourNameToSomebodyElses(Fixture):
    """Interest is offering too, so it carries the same attestation."""

    def setUp(self):
        super().setUp()
        from site_app.models import Posting

        with tenant_context(self.plain):
            self.posting = Posting.objects.create(
                organization=self.plain, member=self.ada,
                kind=Posting.OFFER, description="A panel needs looking at.")
        set_tenant(None)

    def test_a_licensed_member_must_affirm(self):
        from site_app.models import Interest

        self.give_licence(self.sparks)
        self.sign_in(self.dana.user)
        self.client.post(f"/board/{self.posting.id}/interested/", {"hours": "2"})

        with tenant_context(self.sparks):
            self.assertEqual(Interest.objects.count(), 0)

    def test_affirming_records_it(self):
        from site_app.models import Interest

        self.give_licence(self.sparks)
        self.sign_in(self.dana.user)
        self.client.post(f"/board/{self.posting.id}/interested/",
                         {"hours": "2", "under_licence": "1"})

        with tenant_context(self.sparks):
            self.assertEqual(Interest.objects.get().offered_under,
                             "Electrical contractor licence (SC LLR)")

    def test_an_unlicensed_member_is_asked_nothing(self):
        from site_app.models import Interest

        self.sign_in(self.ada.user)
        self.client.post(f"/board/{self.posting.id}/interested/", {})

        with tenant_context(self.plain):
            self.assertEqual(Interest.objects.get().offered_under, "")


class ItIsNotARank(Fixture):
    def test_nothing_orders_or_filters_by_it(self):
        """A licence that moved offers up the feed would make the board a
        directory of tradespeople, and the feed is ordered by need."""
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[2]
        offenders = []
        for path in root.rglob("*.py"):
            if "migrations" in path.parts or "tests" in path.parts:
                continue
            text = path.read_text()
            if re.search(r"order_by\([^)]*offered_under|"
                         r"filter\([^)]*offered_under|"
                         r"exclude\([^)]*offered_under", text):
                offenders.append(str(path.relative_to(root)))
        self.assertEqual(offenders, [])

    def test_the_snapshot_refuses_rather_than_storing_a_blank(self):
        """A blank stored for a licensed organization would afterwards be
        indistinguishable from an offer by somebody holding nothing."""
        self.give_licence(self.sparks)
        with self.assertRaises(LicenceNotAffirmed):
            snapshot(self.sparks, False)
