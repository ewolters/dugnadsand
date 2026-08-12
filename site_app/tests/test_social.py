"""Sharing without a scoreboard, and pairing without ranking anybody.

Most of what follows asserts absences, because this is the part of the system
where the familiar version of the feature is the harmful one.

No like — a like count is a public number attached to a person's contribution,
which is a score wearing a warmer word. Thanks replaces it and is deliberately
NOT STORED: with no row, "never counted" stops being a promise about restraint
and becomes a fact about the schema.

And the pairing utilities join RECORDS, never people. A need with a date
approaching. A bill of materials line and stock in the same unit. Nothing reads
a member in order to decide what to surface, so nothing can rank one.
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from site_app.models import (Comment, MaterialNeed, Member, Organization, Pin,
                             Posting, Project, StockLine, Warehouse)
from site_app.tenancy import tenant_context

from .helpers import SignedIn


class SocialBase(SignedIn, TestCase):
    def setUp(self):
        self.alpha = Organization.objects.create(slug="alpha", name="Alpha Mutual Aid")
        self.ada_user = User.objects.create_user(
            "ada", email="ada@example.test", password="dugnad-test-pw")
        self.ola_user = User.objects.create_user(
            "ola", email="ola@example.test", password="dugnad-test-pw")

        with tenant_context(self.alpha):
            self.ada = Member.objects.create(
                organization=self.alpha, display_name="Ada", user=self.ada_user)
            self.ola = Member.objects.create(
                organization=self.alpha, display_name="Ola", user=self.ola_user)
            self.homes = Project.objects.create(
                organization=self.alpha, started_by=self.ada,
                name="Repairing homes", description="Roofs and ramps.")
            self.ride = Posting.objects.create(
                organization=self.alpha, member=self.ada, kind=Posting.NEED,
                description="A ride to the clinic.")


class ThereIsNoLike(SocialBase):
    """The feature that is not built, asserted so it stays unbuilt."""

    def test_no_model_records_a_reaction(self):
        from django.apps import apps

        names = {m.__name__.lower() for m in apps.get_models()}
        for forbidden in ("like", "reaction", "vote", "upvote", "favourite",
                          "favorite", "star", "heart", "endorsement"):
            self.assertNotIn(forbidden, names)

    def test_no_field_anywhere_counts_approval(self):
        from django.apps import apps

        for model in apps.get_models():
            if not model.__module__.startswith("site_app"):
                continue
            for f in model._meta.get_fields():
                name = getattr(f, "name", "").lower()
                for forbidden in ("likes", "like_count", "score", "rating",
                                  "popularity", "reactions", "votes"):
                    self.assertNotIn(forbidden, name,
                                     f"{model.__name__}.{name}")

    def test_no_url_offers_one(self):
        from site_app import urls

        routes = {str(p.pattern) for p in urls.urlpatterns}
        for forbidden in ("like/", "vote/", "react/"):
            self.assertNotIn(forbidden, routes)


class ThanksLeavesNothingBehind(SocialBase):
    """The refusal that turned out better than the feature it replaced."""

    def test_thanks_is_not_a_model(self):
        """A row with a sender and a recipient has two foreign keys to Member,
        which no-exchange flags on sight. The honest fix was not to soften the
        check but to stop storing the thing."""
        from django.apps import apps

        self.assertNotIn("thanks", {m.__name__.lower() for m in apps.get_models()})

    def test_saying_thanks_writes_no_row_anywhere(self):
        from django.apps import apps

        from site_app.services_social import say_thanks

        with tenant_context(self.alpha):
            # Inside the tenant. Counted outside it, row-level security hides
            # everything and the baseline is zero — so the fixtures created in
            # setUp read as growth caused by saying thanks. Third time this
            # trap has bitten: any count is a query, and a query needs a tenant.
            counts = {m: m.objects.count() for m in apps.get_models()
                      if m.__module__.startswith("site_app")}

            with patch("kjerne_platform.notify.send"):
                say_thanks(to_member=self.ola, from_member=self.ada)

            for model, before in counts.items():
                self.assertEqual(model.objects.count(), before,
                                 f"{model.__name__} grew")

    def test_saying_thanks_sends_one_notice_naming_nobody(self):
        from site_app.services_social import say_thanks

        with tenant_context(self.alpha):
            with patch("kjerne_platform.notify.send") as send:
                say_thanks(to_member=self.ola, from_member=self.ada)

        self.assertEqual(send.call_count, 1)
        recipient, _site, _kind, message = send.call_args.args[:4]
        self.assertEqual(recipient, "ola@example.test")
        self.assertNotIn("Ada", message)

    def test_it_returns_nothing_because_there_is_nothing_to_return(self):
        from site_app.services_social import say_thanks

        with tenant_context(self.alpha):
            with patch("kjerne_platform.notify.send"):
                self.assertIsNone(
                    say_thanks(to_member=self.ola, from_member=self.ada))

    def test_you_cannot_thank_yourself_into_anything(self):
        from site_app.services_social import say_thanks

        with tenant_context(self.alpha):
            with patch("kjerne_platform.notify.send") as send:
                say_thanks(to_member=self.ada, from_member=self.ada)
        self.assertEqual(send.call_count, 0)

    def test_a_broken_notice_service_does_not_break_the_page(self):
        from site_app.services_social import say_thanks

        with tenant_context(self.alpha):
            with patch("kjerne_platform.notify.send",
                       side_effect=RuntimeError("down")):
                say_thanks(to_member=self.ola, from_member=self.ada)


class PinsArePrivate(SocialBase):
    def test_a_pin_is_visible_to_its_owner_and_nobody_else(self):
        from site_app.services_social import pinned_for, toggle_pin

        with tenant_context(self.alpha):
            toggle_pin(member=self.ada, posting=self.ride)

            self.assertEqual(pinned_for(self.ada).count(), 1)
            self.assertEqual(pinned_for(self.ola).count(), 0)

    def test_pinning_twice_unpins(self):
        from site_app.services_social import toggle_pin

        with tenant_context(self.alpha):
            self.assertTrue(toggle_pin(member=self.ada, posting=self.ride))
            self.assertFalse(toggle_pin(member=self.ada, posting=self.ride))
            self.assertEqual(Pin.objects.count(), 0)

    def test_no_page_shows_how_many_people_pinned_something(self):
        """A public pin count is a like with a different label."""
        from site_app.services_social import toggle_pin

        with tenant_context(self.alpha):
            toggle_pin(member=self.ada, posting=self.ride)
            toggle_pin(member=self.ola, posting=self.ride)

        self.sign_in(self.ola_user)
        for url in ("/board/", "/pinned/"):
            body = self.client.get(url).content.decode().lower()
            for phrase in ("2 people", "pinned by", "pin count", "2 pins"):
                self.assertNotIn(phrase, body, url)

    def test_a_pin_belongs_to_exactly_one_thing(self):
        from site_app.services_social import toggle_pin

        with tenant_context(self.alpha):
            with self.assertRaises(ValueError):
                toggle_pin(member=self.ada)
            with self.assertRaises(ValueError):
                toggle_pin(member=self.ada, posting=self.ride, project=self.homes)


class CommentsAreConversation(SocialBase):
    def test_a_comment_needs_exactly_one_parent(self):
        from site_app.services_social import add_comment

        with tenant_context(self.alpha):
            with self.assertRaises(ValueError):
                add_comment(member=self.ada, body="hello")
            with self.assertRaises(ValueError):
                add_comment(member=self.ada, body="hello",
                            posting=self.ride, project=self.homes)

    def test_comments_are_ordered_by_time_and_nothing_else(self):
        """Ordering by anything else is ranking, and ranking conversation is
        how a comment thread becomes a leaderboard."""
        self.assertEqual(tuple(Comment._meta.ordering), ("created_at",))

    def test_a_comment_carries_no_reaction_of_any_kind(self):
        names = {f.name for f in Comment._meta.get_fields()}
        self.assertEqual(
            names & {"likes", "score", "votes", "reactions", "pinned"}, set())

    def test_posting_one_through_the_page_works(self):
        self.sign_in(self.ola_user)
        response = self.client.post("/comment/", {
            "project": str(self.homes.id), "body": "I have a truck Thursday."})

        self.assertEqual(response.status_code, 302)
        with tenant_context(self.alpha):
            self.assertEqual(Comment.objects.count(), 1)

    def test_an_empty_comment_is_refused(self):
        self.sign_in(self.ola_user)
        response = self.client.post("/comment/", {
            "project": str(self.homes.id), "body": "   "})
        self.assertEqual(response.status_code, 400)


class PairingJoinsRecordsNotPeople(SocialBase):
    """The line that keeps this coordination rather than gating."""

    def test_no_pairing_function_reads_a_member(self):
        """Structural. If one of these ever needs to know who somebody is in
        order to decide what to surface, it has stopped being coordination —
        and that change would start by taking a member argument."""
        import inspect

        from site_app import services_social

        for name in ("running_out", "fillable_needs", "going_quiet"):
            params = set(inspect.signature(
                getattr(services_social, name)).parameters)
            self.assertEqual(params & {"member", "for_member", "viewer"}, set(),
                             f"{name} takes a person")

    def test_no_pairing_function_touches_the_contribution_ledger(self):
        import inspect

        from site_app import services_social

        source = inspect.getsource(services_social)
        body = source.split("# Pairing facts")[-1]
        self.assertNotIn("Contribution", body)

    def test_running_out_finds_urgent_needs_nobody_has_taken(self):
        from site_app.services import claim_posting
        from site_app.services_social import running_out

        with tenant_context(self.alpha):
            soon = Posting.objects.create(
                organization=self.alpha, member=self.ada, kind=Posting.NEED,
                description="ride tomorrow",
                needed_by=date.today() + timedelta(days=1))
            covered = Posting.objects.create(
                organization=self.alpha, member=self.ada, kind=Posting.NEED,
                description="already handled",
                needed_by=date.today() + timedelta(days=1))
            claim_posting(posting=covered, member=self.ola)
            Posting.objects.create(
                organization=self.alpha, member=self.ada, kind=Posting.NEED,
                description="not for weeks",
                needed_by=date.today() + timedelta(days=30))

            found = [p.description for p in running_out()]

        self.assertIn("ride tomorrow", found)
        self.assertNotIn("already handled", found)
        self.assertNotIn("not for weeks", found)

    def test_fillable_matches_on_unit_never_on_description(self):
        """Matching descriptions would need a vocabulary of materials, and a
        vocabulary makes two donations comparable. Units are words members
        typed; matching equal ones compares two facts, not two categories."""
        from site_app.services_social import fillable_needs

        with tenant_context(self.alpha):
            barn = Warehouse.objects.create(
                organization=self.alpha, holder=self.ada, name="Barn",
                address="here")
            StockLine.objects.create(
                organization=self.alpha, warehouse=barn,
                description="Totally unrelated pine", quantity=Decimal("300.00"),
                unit="board-feet", confirmed_at=timezone.now(),
                confirmed_by=self.ada)
            need = MaterialNeed.objects.create(
                organization=self.alpha, project=self.homes,
                description="Reclaimed oak", quantity=Decimal("200.00"),
                unit="board-feet", added_by=self.ada)
            mismatched = MaterialNeed.objects.create(
                organization=self.alpha, project=self.homes,
                description="Reclaimed oak", quantity=Decimal("5.00"),
                unit="pallets", added_by=self.ada)

            paired = {n.id for n, _ in fillable_needs()}

        # Descriptions disagree entirely and it still pairs, because the unit
        # is the fact being matched.
        self.assertIn(need.id, paired)
        self.assertNotIn(mismatched.id, paired)

    def test_a_satisfied_need_stops_being_offered(self):
        from site_app.models import MaterialGiven
        from site_app.services_social import fillable_needs

        with tenant_context(self.alpha):
            barn = Warehouse.objects.create(
                organization=self.alpha, holder=self.ada, name="Barn",
                address="here")
            StockLine.objects.create(
                organization=self.alpha, warehouse=barn, description="oak",
                quantity=Decimal("300.00"), unit="board-feet",
                confirmed_at=timezone.now(), confirmed_by=self.ada)
            need = MaterialNeed.objects.create(
                organization=self.alpha, project=self.homes, description="oak",
                quantity=Decimal("200.00"), unit="board-feet", added_by=self.ada)
            MaterialGiven.objects.create(
                organization=self.alpha, need=need, member=self.ola,
                quantity=Decimal("200.00"))

            self.assertEqual(fillable_needs(), [])

    def test_going_quiet_finds_stock_nobody_has_confirmed(self):
        from site_app.services_social import going_quiet

        with tenant_context(self.alpha):
            barn = Warehouse.objects.create(
                organization=self.alpha, holder=self.ada, name="Barn",
                address="here")
            fresh = StockLine.objects.create(
                organization=self.alpha, warehouse=barn, description="fresh",
                quantity=Decimal("1.00"), unit="x",
                confirmed_at=timezone.now(), confirmed_by=self.ada)
            old = StockLine.objects.create(
                organization=self.alpha, warehouse=barn, description="old",
                quantity=Decimal("1.00"), unit="x",
                confirmed_at=timezone.now(), confirmed_by=self.ada)
            StockLine.objects.filter(pk=old.pk).update(
                confirmed_at=timezone.now() - timedelta(days=40))

            found = [line.description for line in going_quiet()]

        self.assertIn("old", found)
        self.assertNotIn("fresh", found)

    def test_the_page_renders_and_ranks_no_member(self):
        self.sign_in(self.ola_user)
        body = self.client.get("/pairings/").content.decode().lower()

        self.assertIn("worth a look", body)
        for phrase in ("most active", "top ", "best match", "recommended for you",
                       "suitable", "reliability"):
            self.assertNotIn(phrase, body)


class PointingSomebodyAtSomething(SocialBase):
    """"I thought of you" — and the sender learns nothing at all.

    Rebuilt from an invitation flow that could not work: it emailed a stranger
    two links, one of which claimed a posting, but a claim needs a Member, a
    stranger is not one, and Member carries no email of its own. Redemption
    raised TypeError and the page said "that link is no longer usable".

    The people worth pointing at are members, and members have accounts. That
    is a notice, not a capability.
    """

    def test_pointing_sends_one_notice_to_that_person(self):
        from site_app.services_social import point_at

        with tenant_context(self.alpha):
            with patch("kjerne_platform.notify.send") as send:
                point_at(posting=self.ride, to_member=self.ola,
                         from_member=self.ada)

        self.assertEqual({c.args[0] for c in send.call_args_list},
                         {"ola@example.test"})

    def test_it_returns_nothing_so_no_caller_can_show_reach(self):
        """A count of who was reached is a delivery receipt, and a delivery
        receipt is the first half of knowing somebody said no."""
        from site_app.services_social import point_at

        with tenant_context(self.alpha):
            with patch("kjerne_platform.notify.send"):
                self.assertIsNone(point_at(posting=self.ride, to_member=self.ola,
                                           from_member=self.ada))

    def test_the_notice_names_neither_the_posting_nor_the_sender(self):
        from site_app.services_social import point_at

        with tenant_context(self.alpha):
            with patch("kjerne_platform.notify.send") as send:
                point_at(posting=self.ride, to_member=self.ola,
                         from_member=self.ada)

        message = send.call_args_list[0].args[3]
        self.assertNotIn("clinic", message.lower())
        self.assertNotIn("Ada", message)

    def test_you_cannot_point_at_yourself_or_at_whoever_posted_it(self):
        from site_app.services_social import point_at

        with tenant_context(self.alpha):
            with patch("kjerne_platform.notify.send") as send:
                point_at(posting=self.ride, to_member=self.ada,
                         from_member=self.ada)          # yourself
                point_at(posting=self.ride, to_member=self.ada,
                         from_member=self.ola)          # the poster
        self.assertEqual(send.call_count, 0)

    def test_nothing_is_stored_about_who_was_pointed_at_what(self):
        """A record of "Ada asked Ola and Ola did nothing" is the obligation
        this system does not have. Same reasoning as thanks."""
        from django.apps import apps

        from site_app.services_social import point_at

        with tenant_context(self.alpha):
            counts = {m: m.objects.count() for m in apps.get_models()
                      if m.__module__.startswith("site_app")}
            with patch("kjerne_platform.notify.send"):
                point_at(posting=self.ride, to_member=self.ola,
                         from_member=self.ada)
            for model, before in counts.items():
                self.assertEqual(model.objects.count(), before,
                                 f"{model.__name__} grew")

    def test_the_posting_offers_it_and_says_what_you_will_not_learn(self):
        """Moved off the feed and onto the posting itself.

        Pointing somebody at something is a considered act — the control was
        already folded away behind a summary for that reason — and repeating
        it on every card of a scrolling feed made it ambient instead. It lives
        where somebody has stopped to read the thing.
        """
        self.sign_in(self.ola_user)
        body = self.client.get(f"/board/{self.ride.id}/").content.decode()

        self.assertIn(f"/board/{self.ride.id}/point/", body)
        self.assertIn("will not be told", body.replace("\n", " "))

    def test_the_picker_is_not_narrowed_by_what_anybody_has_given(self):
        """A list of who to ask, ordered or filtered by contribution, would be
        the ledger deciding who gets asked."""
        import inspect

        from site_app import views

        source = inspect.getsource(views.board)
        self.assertNotIn("Contribution", source)

    def test_sending_it_through_the_page_works(self):
        self.sign_in(self.ola_user)
        with patch("kjerne_platform.notify.send") as send:
            response = self.client.post(f"/board/{self.ride.id}/point/",
                                        {"member": str(self.ola.id)})
        self.assertEqual(response.status_code, 302)
        # Ola pointing at Ola is a no-op; the route still works.
        self.assertEqual(send.call_count, 0)
