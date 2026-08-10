"""@ somebody, $ something.

The load-bearing tests are the ones about what is NOT kept. A mention is
resolved when the page is drawn and never written down: a row joining a
comment to a member would be countable, and "Ada was mentioned forty times" is
a popularity score arriving through a door nobody was watching.

The rest is about being wrong safely. Ambiguity stays plain text, because
guessing would notify somebody who was not being spoken to. And the body is
user input, so escaping happens before any anchor is built.
"""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from site_app import mentions
from site_app.models import (Member, Organization, Posting, Project,
                             StockLine, Warehouse)
from site_app.tenancy import tenant_context

from .helpers import SignedIn


class MentionBase(SignedIn, TestCase):
    def setUp(self):
        self.alpha = Organization.objects.create(slug="alpha", name="Alpha")
        self.beta = Organization.objects.create(slug="beta", name="Beta")

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
            self.homes = Project.objects.create(
                organization=self.alpha, started_by=self.ada,
                name="Repairing homes", description="Roofs.")
            self.barn = Warehouse.objects.create(
                organization=self.alpha, holder=self.ada, name="North barn",
                address="Gate 4412")
            self.lumber = StockLine.objects.create(
                organization=self.alpha, warehouse=self.barn,
                description="Reclaimed oak, 2x8", quantity=Decimal("200.00"),
                unit="board-feet", confirmed_at=timezone.now(),
                confirmed_by=self.ada)

        with tenant_context(self.beta):
            Member.objects.create(organization=self.beta, display_name="Bo",
                                  user=self.bo_user)


class NothingIsWrittenDown(MentionBase):
    """The one that keeps this from becoming a scoreboard."""

    def test_there_is_no_mention_model(self):
        from django.apps import apps

        names = {m.__name__.lower() for m in apps.get_models()}
        for forbidden in ("mention", "commentmention", "tag", "commenttag"):
            self.assertNotIn(forbidden, names)

    def test_commenting_with_mentions_writes_only_the_comment(self):
        from django.apps import apps

        from site_app.models import Comment
        from site_app.services_social import add_comment

        with tenant_context(self.alpha):
            counts = {m: m.objects.count() for m in apps.get_models()
                      if m.__module__.startswith("site_app")}
            with patch("kjerne_platform.notify.send"):
                add_comment(member=self.ada, project=self.homes,
                            body="@Ola can you bring $oak")

            for model, before in counts.items():
                expected = before + (1 if model is Comment else 0)
                self.assertEqual(model.objects.count(), expected,
                                 f"{model.__name__}")

    def test_the_body_is_stored_exactly_as_typed(self):
        """The text is the record. Rewriting it into markup on the way in
        would make the stored comment depend on who existed that day."""
        from site_app.models import Comment
        from site_app.services_social import add_comment

        written = "@Ola can you bring $oak"
        with tenant_context(self.alpha):
            with patch("kjerne_platform.notify.send"):
                add_comment(member=self.ada, project=self.homes, body=written)
            self.assertEqual(Comment.objects.get().body, written)


class ResolvingThem(MentionBase):
    def test_a_person_who_resolves_is_marked(self):
        with tenant_context(self.alpha):
            html = mentions.render("thanks @Ola")
        self.assertIn('class="mention person"', html)

    def test_a_resource_links_to_where_it_is(self):
        with tenant_context(self.alpha):
            html = mentions.render("we have $oak")
        self.assertIn(f'href="/warehouse/{self.barn.id}/"', html)

    def test_something_that_matches_nothing_stays_as_typed(self):
        with tenant_context(self.alpha):
            html = mentions.render("@Nobody has $unobtainium")
        self.assertIn("@Nobody", html)
        self.assertIn("$unobtainium", html)
        self.assertNotIn("mention", html)

    def test_an_ambiguous_name_is_left_alone(self):
        """Guessing would notify somebody who was not being spoken to."""
        with tenant_context(self.alpha):
            Member.objects.create(organization=self.alpha, display_name="Adam")
            html = mentions.render("@Ad who?")
        self.assertNotIn("mention", html)

    def test_ambiguous_stock_is_left_alone_too(self):
        with tenant_context(self.alpha):
            StockLine.objects.create(
                organization=self.alpha, warehouse=self.barn,
                description="Green oak beams", quantity=Decimal("10.00"),
                unit="pieces", confirmed_at=timezone.now(), confirmed_by=self.ada)
            html = mentions.render("bring $oak")
        self.assertNotIn("mention", html)

    def test_stock_that_is_gone_degrades_to_plain_text(self):
        """An old comment should tell the truth: whatever that was, it is not
        on the shelf now. A stored link would rot into a dangling id."""
        with tenant_context(self.alpha):
            self.lumber.available = False
            self.lumber.save(update_fields=["available"])
            html = mentions.render("we had $oak")
        self.assertIn("$oak", html)
        self.assertNotIn("mention", html)

    def test_a_member_of_another_organization_never_resolves(self):
        with tenant_context(self.alpha):
            html = mentions.render("@Bo are you there")
        self.assertNotIn("mention", html)


class TellingThePersonNamed(MentionBase):
    def test_being_named_sends_one_notice(self):
        from site_app.services_social import add_comment

        with tenant_context(self.alpha):
            with patch("kjerne_platform.notify.send") as send:
                add_comment(member=self.ada, project=self.homes,
                            body="@Ola thoughts?")

        self.assertEqual({c.args[0] for c in send.call_args_list},
                         {"ola@example.test"})

    def test_the_notice_carries_none_of_the_comment(self):
        from site_app.services_social import add_comment

        with tenant_context(self.alpha):
            with patch("kjerne_platform.notify.send") as send:
                add_comment(member=self.ada, project=self.homes,
                            body="@Ola the clinic run is Thursday")

        message = send.call_args_list[0].args[3]
        self.assertNotIn("clinic", message)
        self.assertNotIn("Ada", message)

    def test_naming_somebody_three_times_asks_once(self):
        with tenant_context(self.alpha):
            found = mentions.mentioned_members("@Ola @Ola @Ola")
        self.assertEqual(len(found), 1)

    def test_naming_yourself_notifies_nobody(self):
        from site_app.services_social import add_comment

        with tenant_context(self.alpha):
            with patch("kjerne_platform.notify.send") as send:
                add_comment(member=self.ada, project=self.homes,
                            body="@Ada talking to myself")
        self.assertEqual(send.call_count, 0)


class TheBodyIsUntrusted(MentionBase):
    """A comment is user input and this builds HTML out of it."""

    def test_markup_in_a_comment_is_escaped(self):
        with tenant_context(self.alpha):
            html = mentions.render('<script>alert(1)</script>')
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_markup_next_to_a_mention_is_still_escaped(self):
        """Escaping happens BEFORE any anchor is built, so a mention cannot
        be used to smuggle markup past it."""
        with tenant_context(self.alpha):
            html = mentions.render('@Ola <img src=x onerror=alert(1)>')
        self.assertIn('class="mention person"', html)
        self.assertNotIn("<img", html)

    def test_a_quote_in_a_display_name_cannot_break_an_attribute(self):
        with tenant_context(self.alpha):
            Member.objects.create(organization=self.alpha,
                                  display_name='Zed" onmouseover="x')
            html = mentions.render("@Zed hello")
        self.assertNotIn('onmouseover="x"', html)

    def test_it_renders_through_the_page(self):
        from site_app.services_social import add_comment

        with tenant_context(self.alpha):
            with patch("kjerne_platform.notify.send"):
                add_comment(member=self.ada, project=self.homes,
                            body="@Ola bring $oak")

        self.sign_in(self.ola_user)
        body = self.client.get(f"/projects/{self.homes.id}/").content.decode()
        self.assertIn('class="mention person"', body)
        self.assertIn(f'href="/warehouse/{self.barn.id}/"', body)
