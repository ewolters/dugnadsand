"""Stopping, and letting a posting leave the board.

"You can stop whenever, and nothing is recorded" was a rule in a document with
no button behind it. These tests cover the button, and — more to the point —
they cover the second half of the sentence, which is the part that could be
quietly broken by anybody adding perfectly reasonable history-keeping.

They also cover a defect the timing feature introduced and could not show until
something expired: needs sort by needed_by ascending, so overdue ones sorted
FIRST and the top of the board filled with dead items.
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from site_app.models import Claim, Contribution, Member, Organization, Posting
from site_app.tenancy import tenant_context

from .helpers import SignedIn


class SteppingOffBase(SignedIn, TestCase):
    def setUp(self):
        self.alpha = Organization.objects.create(slug="alpha", name="Alpha Mutual Aid")

        def member(username, name, email):
            user = User.objects.create_user(username, email=email,
                                            password="dugnad-test-pw")
            with tenant_context(self.alpha):
                return user, Member.objects.create(
                    organization=self.alpha, display_name=name, user=user)

        self.ada_user, self.ada = member("ada", "Ada", "ada@example.test")
        self.ola_user, self.ola = member("ola", "Ola", "ola@example.test")
        self.kit_user, self.kit = member("kit", "Kit", "kit@example.test")

        with tenant_context(self.alpha):
            self.ride = Posting.objects.create(
                organization=self.alpha, member=self.ada, kind=Posting.NEED,
                description="A ride to the clinic on Thursday.")

    def claim(self, member, posting=None):
        from site_app.services import claim_posting
        with tenant_context(self.alpha):
            return claim_posting(posting=posting or self.ride, member=member)


class StoppingLeavesNoTrace(SteppingOffBase):
    """The design decision, and the one worth defending hardest."""

    def test_stepping_off_removes_the_claim_entirely(self):
        self.claim(self.ola)
        self.sign_in(self.ola_user)

        response = self.client.post(f"/board/{self.ride.id}/step-off/")

        self.assertEqual(response.status_code, 302)
        with tenant_context(self.alpha):
            self.assertEqual(Claim.objects.filter(posting=self.ride).count(), 0)

    def test_no_field_anywhere_could_record_that_somebody_stopped(self):
        """A hard delete is only half of it. The responsible-looking version of
        this feature is a withdrawn flag or a stepped_off_at timestamp, and
        either one is a record of not following through — countable, therefore
        a reliability score, therefore standing. no-obligation forbids the
        field names; this asserts it at the model."""
        names = set()
        for model in (Posting, Claim, Contribution):
            names |= {f.name for f in model._meta.get_fields()}

        for forbidden in ("withdrawn", "withdrawn_at", "stepped_off",
                          "stepped_off_at", "abandoned", "abandoned_at",
                          "cancelled", "no_show", "reliability", "dropped"):
            self.assertNotIn(forbidden, names)

    def test_stepping_off_twice_changes_nothing_and_says_so(self):
        self.claim(self.ola)
        self.sign_in(self.ola_user)
        self.client.post(f"/board/{self.ride.id}/step-off/")

        again = self.client.post(f"/board/{self.ride.id}/step-off/")
        self.assertEqual(again.status_code, 400)

    def test_hours_already_given_survive_stepping_off(self):
        """Work that happened is a fact about the world, not a commitment.
        Contribution points at the posting and never at the claim, so this
        holds structurally — the test pins that it stays that way."""
        from site_app.services import record_contribution

        self.claim(self.ola)
        with tenant_context(self.alpha):
            record_contribution(posting=self.ride, member=self.ola,
                                hours=Decimal("2.00"), note="Drove halfway.")

        self.sign_in(self.ola_user)
        self.client.post(f"/board/{self.ride.id}/step-off/")

        with tenant_context(self.alpha):
            self.assertEqual(
                Contribution.objects.filter(posting=self.ride).count(), 1)


class OnlyYourOwn(SteppingOffBase):
    def test_you_cannot_step_somebody_else_off(self):
        self.claim(self.ola)
        self.sign_in(self.kit_user)

        response = self.client.post(f"/board/{self.ride.id}/step-off/")

        self.assertEqual(response.status_code, 400)
        with tenant_context(self.alpha):
            self.assertEqual(Claim.objects.filter(posting=self.ride).count(), 1)

    def test_the_poster_cannot_remove_whoever_answered(self):
        """Letting the person who asked remove the person helping would make
        them a manager of their own helpers. There is no such role here."""
        self.claim(self.ola)
        self.sign_in(self.ada_user)  # Ada posted it.

        response = self.client.post(f"/board/{self.ride.id}/step-off/")

        self.assertEqual(response.status_code, 400)
        with tenant_context(self.alpha):
            self.assertEqual(Claim.objects.filter(posting=self.ride).count(), 1)


class TellingThePosterWithoutBlamingAnyone(SteppingOffBase):
    def test_the_poster_hears_only_when_the_last_person_leaves(self):
        self.claim(self.ola)
        self.claim(self.kit)

        self.sign_in(self.ola_user)
        with patch("kjerne_platform.notify.send") as send:
            self.client.post(f"/board/{self.ride.id}/step-off/")
        self.assertEqual(send.call_count, 0, "still covered is not news")

        self.sign_in(self.kit_user)
        with patch("kjerne_platform.notify.send") as send:
            self.client.post(f"/board/{self.ride.id}/step-off/")
        self.assertEqual({c.args[0] for c in send.call_args_list},
                         {"ada@example.test"})

    def test_the_notice_describes_the_posting_not_the_person_who_left(self):
        """An event has a subject. A notice whose subject is somebody who
        stopped is a notice that they let you down, which puts back the
        obligation stepping off exists to remove."""
        self.claim(self.ola)
        self.sign_in(self.ola_user)

        with patch("kjerne_platform.notify.send") as send:
            self.client.post(f"/board/{self.ride.id}/step-off/")

        message = send.call_args_list[0].args[3]
        self.assertNotIn("Ola", message)
        for blaming in ("stepped off", "left", "dropped", "withdrew",
                        "cancelled", "no longer helping"):
            self.assertNotIn(blaming, message.lower())

    def test_a_broken_notice_service_still_lets_you_stop(self):
        self.claim(self.ola)
        self.sign_in(self.ola_user)

        with patch("kjerne_platform.notify.send", side_effect=RuntimeError("down")):
            response = self.client.post(f"/board/{self.ride.id}/step-off/")

        self.assertEqual(response.status_code, 302)
        with tenant_context(self.alpha):
            self.assertEqual(Claim.objects.filter(posting=self.ride).count(), 0)


class TheBoardOffersIt(SteppingOffBase):
    def test_someone_on_a_posting_is_offered_a_way_off_and_not_a_second_claim(self):
        self.claim(self.ola)
        self.sign_in(self.ola_user)

        body = self.client.get("/board/").content.decode()

        self.assertIn(f"/board/{self.ride.id}/step-off/", body)
        self.assertNotIn(f"/board/{self.ride.id}/claim/", body)

    def test_someone_not_on_it_is_offered_the_claim_and_no_way_off(self):
        self.sign_in(self.kit_user)

        body = self.client.get("/board/").content.decode()

        self.assertIn(f"/board/{self.ride.id}/claim/", body)
        self.assertNotIn(f"/board/{self.ride.id}/step-off/", body)


class ExpiredNeedsStopOutrankingLiveOnes(SteppingOffBase):
    """The defect the timing feature shipped with.

    needed_by ascending puts the oldest date first, so overdue needs sorted
    into the most prominent position on the board and the problem compounded
    the longer the site ran.
    """

    def need(self, text, needed_by=None):
        with tenant_context(self.alpha):
            return Posting.objects.create(
                organization=self.alpha, member=self.ada, kind=Posting.NEED,
                description=text, needed_by=needed_by)

    def test_a_live_need_outranks_an_expired_one(self):
        today = date.today()
        self.need("expired need", needed_by=today - timedelta(days=10))
        self.need("live need", needed_by=today + timedelta(days=3))

        self.sign_in(self.kit_user)
        body = self.client.get("/board/").content.decode()

        self.assertLess(body.index("live need"), body.index("expired need"))

    def test_an_expired_need_still_outranks_an_undated_one_and_is_not_hidden(self):
        """A slipped date does not mean the ride stopped being wanted. Dropping
        a real need would be worse than listing it late."""
        self.need("undated need")
        self.need("expired need", needed_by=date.today() - timedelta(days=10))

        self.sign_in(self.kit_user)
        body = self.client.get("/board/").content.decode()

        self.assertIn("expired need", body)
        self.assertLess(body.index("expired need"), body.index("undated need"))

    def test_the_ordering_holds_however_many_have_expired(self):
        """The compounding version: a graveyard must not bury one live need."""
        today = date.today()
        for i in range(6):
            self.need(f"expired {i}", needed_by=today - timedelta(days=i + 1))
        self.need("the live one", needed_by=today + timedelta(days=1))

        self.sign_in(self.kit_user)
        body = self.client.get("/board/").content.decode()

        self.assertLess(body.index("the live one"), body.index("expired 0"))


class AskingTheirPosterAboutIt(SteppingOffBase):
    def test_the_poster_is_asked_about_their_own_expired_posting(self):
        with tenant_context(self.alpha):
            Posting.objects.create(
                organization=self.alpha, member=self.ada, kind=Posting.NEED,
                description="A ride that has passed.",
                needed_by=date.today() - timedelta(days=3))

        self.sign_in(self.ada_user)
        body = self.client.get("/board/").content.decode()
        self.assertIn("Still needed?", body)

    def test_nobody_else_is_shown_that_prompt(self):
        """Asking the room whether somebody else's need is still real would put
        their circumstances up for discussion."""
        with tenant_context(self.alpha):
            Posting.objects.create(
                organization=self.alpha, member=self.ada, kind=Posting.NEED,
                description="A ride that has passed.",
                needed_by=date.today() - timedelta(days=3))

        self.sign_in(self.kit_user)
        body = self.client.get("/board/").content.decode()
        self.assertNotIn("Still needed?", body)

    def test_taking_it_down_records_no_outcome(self):
        """Closing means "off the board", never "this was fulfilled". A stored
        completion is a stored duty that was owed — see no-obligation."""
        with tenant_context(self.alpha):
            posting = Posting.objects.create(
                organization=self.alpha, member=self.ada, kind=Posting.NEED,
                description="A ride.", needed_by=date.today() - timedelta(days=3))

        self.sign_in(self.ada_user)
        self.client.post(f"/board/{posting.id}/close/")

        with tenant_context(self.alpha):
            posting.refresh_from_db()
        self.assertFalse(posting.open)
        fields = {f.name for f in Posting._meta.get_fields()}
        for outcome in ("completed", "completed_at", "fulfilled", "met",
                        "outcome", "resolution", "closed_reason"):
            self.assertNotIn(outcome, fields)
