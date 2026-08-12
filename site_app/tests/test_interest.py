"""Saying you might help, without committing to it.

Between keeping a posting privately and taking it on there was nothing, so
the only public move was the whole commitment. This is the step in between —
and it is the feature most likely to become a like, so most of what is tested
here is that it has not.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from site_app.models import Contribution, Interest, Member, Organization, Posting, Region
from site_app.services_social import express_interest, withdraw_interest
from site_app.tenancy import set_tenant, tenant_context

from .helpers import SignedIn


class InterestBase(SignedIn, TestCase):
    def setUp(self):
        self.chapter = Region.objects.create(slug="up", name="Upstate")
        self.org = Organization.objects.create(
            slug="alpha", name="Alpha", region=self.chapter)
        self.user = User.objects.create_user("ada", password="dugnad-test-pw")
        with tenant_context(self.org):
            self.ada = Member.objects.create(
                organization=self.org, display_name="Ada", user=self.user)
            self.ola = Member.objects.create(
                organization=self.org, display_name="Ola")
            self.need = Posting.objects.create(
                organization=self.org, member=self.ola, kind=Posting.NEED,
                description="A ride to the clinic on Thursday.")
        set_tenant(None)

    def tearDown(self):
        set_tenant(None)


class SayingYouMightHelp(InterestBase):
    def test_it_records_who_without_hours(self):
        """The ordinary case. "I'm interested" says nothing about how long,
        and requiring a number would turn a tentative gesture into an estimate
        somebody has to defend."""
        with tenant_context(self.org):
            interest = express_interest(posting=self.need, member=self.ada)
            self.assertIsNone(interest.hours)
            self.assertEqual(Interest.objects.count(), 1)

    def test_hours_may_be_offered(self):
        with tenant_context(self.org):
            interest = express_interest(posting=self.need, member=self.ada,
                                        hours=Decimal("4.00"))
            self.assertEqual(interest.hours, Decimal("4.00"))

    def test_saying_it_again_revises_rather_than_repeating(self):
        with tenant_context(self.org):
            express_interest(posting=self.need, member=self.ada,
                             hours=Decimal("4.00"))
            express_interest(posting=self.need, member=self.ada,
                             hours=Decimal("2.00"))
            self.assertEqual(Interest.objects.count(), 1)
            self.assertEqual(Interest.objects.first().hours, Decimal("2.00"))

    def test_it_can_be_revised_downward_as_freely_as_up(self):
        """The whole point of a ceiling with no floor. Somebody who realises
        they have less time than they thought must be able to say so without
        it costing them anything."""
        with tenant_context(self.org):
            express_interest(posting=self.need, member=self.ada,
                             hours=Decimal("8.00"))
            express_interest(posting=self.need, member=self.ada, hours=None)
            self.assertIsNone(Interest.objects.first().hours)

    def test_withdrawing_is_a_hard_delete(self):
        """A withdrawn flag would be a record of somebody changing their mind,
        and anything stored can be counted. Nothing should be able to say how
        often a person went quiet."""
        with tenant_context(self.org):
            express_interest(posting=self.need, member=self.ada)
            withdraw_interest(posting=self.need, member=self.ada)
            self.assertEqual(Interest.objects.count(), 0)

    def test_two_people_may_be_interested_in_one_thing(self):
        with tenant_context(self.org):
            express_interest(posting=self.need, member=self.ada)
            express_interest(posting=self.need, member=self.ola)
            self.assertEqual(Interest.objects.count(), 2)


class ItIsNotALike(InterestBase):
    """The failure this feature invites, asserted against rather than hoped
    away. A count of interest is a like; a like is a score."""

    def test_the_model_carries_no_count_and_no_score(self):
        names = {f.name for f in Interest._meta.get_fields()}
        for forbidden in ("count", "score", "rating", "votes", "likes",
                          "weight", "rank", "reactions"):
            self.assertNotIn(forbidden, names, f"Interest grew {forbidden}")

    def test_it_carries_no_floor(self):
        """no-obligation scans this model now. hours is a ceiling; a minimum,
        a commitment or a completion would make stopping cost something."""
        names = {f.name for f in Interest._meta.get_fields()}
        for forbidden in ("hours_min", "minimum", "required", "commitment",
                          "completion", "no_show", "abandoned"):
            self.assertNotIn(forbidden, names, f"Interest grew {forbidden}")

    def test_no_obligation_actually_scans_it(self):
        """The check reads a fixed tuple of model names. A model absent from
        it is ungoverned while the check still reports UPHELD."""
        from policy import checks

        self.assertIn("Interest", checks.DOMAIN_MODELS)
        self.assertEqual(checks.no_obligation().status, checks.UPHELD)

    def test_the_page_names_who_is_interested_and_never_how_many(self):
        with tenant_context(self.org):
            express_interest(posting=self.need, member=self.ola)
        self.sign_in(self.user)

        body = self.client.get("/community/").content.decode()
        self.assertIn("Interested:", body)
        self.assertIn("Ola", body)
        self.assertNotIn("1 interested", body)
        self.assertNotIn("2 interested", body)

    def test_nothing_links_an_interest_to_the_hours_ledger(self):
        """An offer of four hours compared against what was actually given
        would be a shortfall, which is the record no-obligation removes."""
        for field in Interest._meta.get_fields():
            related = getattr(field, "related_model", None)
            self.assertIsNot(related, Contribution,
                             f"Interest.{field.name} reaches the ledger")


class FromThePage(InterestBase):
    def test_a_member_can_say_they_are_interested(self):
        self.sign_in(self.user)
        response = self.client.post(f"/board/{self.need.id}/interested/",
                                    {"back": "/community/"})
        self.assertEqual(response.status_code, 302)
        with tenant_context(self.org):
            self.assertEqual(Interest.objects.filter(member=self.ada).count(), 1)

    def test_hours_can_be_offered_from_the_card(self):
        self.sign_in(self.user)
        self.client.post(f"/board/{self.need.id}/interested/",
                         {"hours": "3.5", "back": "/community/"})
        with tenant_context(self.org):
            self.assertEqual(Interest.objects.first().hours, Decimal("3.50"))

    def test_nonsense_hours_are_refused(self):
        self.sign_in(self.user)
        for bad in ("banana", "-2", "0"):
            response = self.client.post(f"/board/{self.need.id}/interested/",
                                        {"hours": bad})
            self.assertEqual(response.status_code, 400, bad)
        with tenant_context(self.org):
            self.assertEqual(Interest.objects.count(), 0)

    def test_it_can_be_taken_back_from_the_card(self):
        self.sign_in(self.user)
        self.client.post(f"/board/{self.need.id}/interested/", {})
        self.client.post(f"/board/{self.need.id}/interested/", {"withdraw": "1"})
        with tenant_context(self.org):
            self.assertEqual(Interest.objects.count(), 0)

    def test_a_posting_from_another_chapter_cannot_be_marked(self):
        midlands = Region.objects.create(slug="mid", name="Midlands")
        far = Organization.objects.create(slug="far", name="Far", region=midlands)
        with tenant_context(far):
            member = Member.objects.create(organization=far, display_name="Sam")
            theirs = Posting.objects.create(
                organization=far, member=member, kind=Posting.OFFER,
                description="Elsewhere.")
        set_tenant(None)

        self.sign_in(self.user)
        self.assertEqual(
            self.client.post(f"/board/{theirs.id}/interested/").status_code, 404)
