"""One feed, from four places.

The community, projects, days and the warehouse were four streams and only one
of them was a feed. So announcing a work day — a real thing at a real place on
a real Saturday, the most socially significant event this system has — showed
up nowhere anybody was looking.

Two things this file exists to hold:

  THERE IS NO ACTIVITY TABLE. A row per thing-that-happened, stamped with who
  did it, is a countable record of who does the most. It would be a score by
  the end of the first month. The feed is merged at render time from the
  models that already hold the facts, and a test greps the models to keep it
  that way.

  ORDERING STILL NEVER CONSULTS THE PERSON. A day sorts by its date and a
  need by its date, because Saturday is Saturday whichever it is. Nothing
  sorts by who wrote it, who has given most, or who has given anything —
  see no-gating and no-routing-by-record.

The first version of the merge INVERTED the bands and put expired needs above
live ones. test_stepping_off.py caught it. The banding is asserted directly
here so the next person to touch it sees what the order is for.
"""

import re
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from site_app.models import (Member, Organization, Posting, Project, Region,
                             WorkDay)
from site_app.tenancy import set_tenant, tenant_context

from .helpers import SignedIn


class FeedBase(SignedIn, TestCase):
    def setUp(self):
        self.region = Region.objects.create(slug="up", name="Upstate")
        self.org = Organization.objects.create(
            slug="ouat", name="Once Upon A Table", region=self.region,
            kind=Organization.AID_GROUP)
        self.hannah = self.member_for(self.org, "hannah", "Hannah")
        set_tenant(None)

    def tearDown(self):
        set_tenant(None)

    def member_for(self, organization, username, display):
        user = User.objects.create_user(username, password="dugnad-test-pw")
        set_tenant(organization.id, organization.region_id)
        member = Member.objects.create(organization=organization, user=user,
                                       display_name=display)
        set_tenant(None)
        return member

    def a_day(self, name="Clear the lot", days=3, announced=True):
        with tenant_context(self.org):
            day = WorkDay.objects.create(
                organization=self.org, called_by=self.hannah, name=name,
                description="Bring gloves.", place="Behind the church",
                starts_at=timezone.now() + timedelta(days=days))
            if announced:
                WorkDay.objects.filter(pk=day.pk).update(
                    published_at=timezone.now())
            return WorkDay.objects.get(pk=day.pk)

    def a_project(self, name="The Pendleton lot"):
        with tenant_context(self.org):
            return Project.objects.create(
                organization=self.org, started_by=self.hannah, name=name,
                description="Clearing and replanting it over the summer.")

    def a_need(self, text, needed_by=None):
        with tenant_context(self.org):
            return Posting.objects.create(
                organization=self.org, member=self.hannah,
                kind=Posting.NEED, description=text, needed_by=needed_by)

    def cards(self):
        """The feed's card bodies, in order."""
        body = self.client.get("/board/").content.decode()
        return re.findall(r'<p class="body">(.*?)</p>', body, re.S)

    def at(self, needle):
        for i, text in enumerate(self.cards()):
            if needle in text:
                return i
        return None


class DaysAndProjectsReachTheFeed(FeedBase):
    def test_an_announced_day_is_on_the_feed(self):
        self.a_day()
        self.sign_in(self.hannah.user)
        body = self.client.get("/board/").content.decode()

        self.assertIn("Clear the lot", body)
        self.assertIn("Behind the church", body)

    def test_you_can_say_you_are_coming_without_leaving_the_feed(self):
        day = self.a_day()
        self.sign_in(self.hannah.user)
        self.assertContains(self.client.get("/board/"),
                            f'action="/days/{day.id}/coming/"')

    def test_an_UNANNOUNCED_day_is_not(self):
        """A day stays off the feed until somebody records that whoever
        holds the gate said yes. Announcing it is the whole point of the
        clearance gate, and a feed that ignored that would route around it."""
        self.a_day(name="Not cleared yet", announced=False)
        self.sign_in(self.hannah.user)
        self.assertNotContains(self.client.get("/board/"), "Not cleared yet")

    def test_a_day_that_has_happened_drops_off(self):
        """It stops being news and lives on /days/."""
        day = self.a_day(name="Last Saturday", days=3)
        with tenant_context(self.org):
            WorkDay.objects.filter(pk=day.pk).update(
                starts_at=timezone.now() - timedelta(days=1))

        self.sign_in(self.hannah.user)
        self.assertNotContains(self.client.get("/board/"), "Last Saturday")

    def test_a_cancelled_day_drops_off(self):
        day = self.a_day(name="Called off one")
        with tenant_context(self.org):
            WorkDay.objects.filter(pk=day.pk).update(
                cancelled_at=timezone.now())

        self.sign_in(self.hannah.user)
        self.assertNotContains(self.client.get("/board/"), "Called off one")

    def test_a_new_project_is_on_the_feed(self):
        """Asserted on the DESCRIPTION, not the name.

        The composer's "part of something ongoing" select lists every open
        project by name, so a name is on this page whether or not the feed
        carries the project — which would have made both this test and its
        negative pass for the wrong reason. Only the card renders the
        description.
        """
        self.a_project()
        self.sign_in(self.hannah.user)
        self.assertContains(self.client.get("/board/"),
                            "Clearing and replanting it over the summer.")

    def test_AN_OLD_PROJECT_IS_NOT(self):
        """A project appears as a story, when it starts, and then lives on
        its own page. Every open project for ever would make the feed a
        directory with the same six items pinned to the bottom of it."""
        project = self.a_project(name="Started last spring")
        with tenant_context(self.org):
            Project.objects.filter(pk=project.pk).update(
                created_at=timezone.now() - timedelta(days=60))

        self.sign_in(self.hannah.user)
        self.assertNotContains(self.client.get("/board/"),
                               "Clearing and replanting it over the summer.")


class TheOrderingContractHolds(FeedBase):
    """The bands, asserted directly. The first version inverted them."""

    def test_a_live_dated_need_leads_an_expired_one(self):
        self.a_need("expired need", needed_by=date.today() - timedelta(days=2))
        self.a_need("live need", needed_by=date.today() + timedelta(days=2))
        self.sign_in(self.hannah.user)

        self.assertLess(self.at("live need"), self.at("expired need"))

    def test_an_expired_need_still_leads_an_undated_one(self):
        """Not hidden. A date slipping does not mean the ride stopped being
        wanted, and quietly dropping a real need would be worse."""
        self.a_need("undated need")
        self.a_need("expired need", needed_by=date.today() - timedelta(days=2))
        self.sign_in(self.hannah.user)

        self.assertLess(self.at("expired need"), self.at("undated need"))

    def test_A_DAY_AND_A_NEED_INTERLEAVE_BY_DATE(self):
        """The point of merging them. Saturday is Saturday whether it is a
        work day or a lift somebody needs, so a day on Thursday leads a need
        due Friday and follows one due Wednesday."""
        self.a_need("need on wednesday", needed_by=date.today() + timedelta(days=1))
        self.a_need("need on friday", needed_by=date.today() + timedelta(days=3))
        self.a_day(name="day on thursday", days=2)
        self.sign_in(self.hannah.user)

        self.assertLess(self.at("need on wednesday"), self.at("Behind the church"))
        self.assertLess(self.at("Behind the church"), self.at("need on friday"))

    def test_a_project_sits_with_the_undated(self):
        self.a_need("dated need", needed_by=date.today() + timedelta(days=1))
        self.a_project(name="a project")
        self.sign_in(self.hannah.user)

        self.assertLess(self.at("dated need"),
                        self.at("Clearing and replanting"))

    def test_ordering_still_ignores_who_wrote_it(self):
        """The invariant the whole system rests on, restated for a feed that
        now carries four kinds of thing."""
        from decimal import Decimal

        from site_app.services import record_contribution

        giver = self.member_for(self.org, "kit", "Kit")
        set_tenant(None)
        with tenant_context(self.org):
            work = Posting.objects.create(
                organization=self.org, member=self.hannah,
                kind=Posting.OFFER, description="Somewhere to put hours.")
            for _ in range(5):
                record_contribution(posting=work, member=giver,
                                    hours=Decimal("8.00"), note="")
            Posting.objects.create(
                organization=self.org, member=giver, kind=Posting.NEED,
                description="kit who has given lots asks", needed_by=None)
            Posting.objects.create(
                organization=self.org, member=self.hannah, kind=Posting.NEED,
                description="hannah who has given none asks",
                needed_by=date.today())

        self.sign_in(self.hannah.user)
        self.assertLess(self.at("hannah who has given none asks"),
                        self.at("kit who has given lots asks"))


class ItNarrowsWithoutReordering(FeedBase):
    """Fixture text here is deliberately odd.

    The first version asked for "a need", which is a phrase this app says in
    ordinary copy — the empty state alone reads "when somebody posts a need"
    — so a negative assertion matched the page's own prose. Test fixtures
    want strings nothing else would ever write.
    """

    NEED = "zucchini for the pickling"

    def test_days_can_be_shown_alone(self):
        self.a_day()
        self.a_need(self.NEED, needed_by=date.today())
        self.sign_in(self.hannah.user)

        body = self.client.get("/board/?show=days").content.decode()
        self.assertIn("Behind the church", body)
        self.assertNotIn(self.NEED, body)

    def test_asking_shows_no_days(self):
        self.a_day()
        self.a_need(self.NEED, needed_by=date.today())
        self.sign_in(self.hannah.user)

        body = self.client.get("/board/?show=asking").content.decode()
        self.assertIn(self.NEED, body)
        self.assertNotIn("Behind the church", body)

    def test_mine_reaches_days_and_projects_too(self):
        """"Mine" is a fact about the row. It would be a strange feed where
        the day you called was not yours."""
        self.a_day()
        self.a_project()
        self.sign_in(self.hannah.user)

        body = self.client.get("/board/?show=mine").content.decode()
        self.assertIn("Behind the church", body)
        self.assertIn("Clearing and replanting", body)


class ThereIsNoActivityTable(TestCase):
    """The table that must not exist.

    A row per thing-that-happened, stamped with who did it, is a countable
    record of who does the most — it would be a score by the end of the first
    month, and no-aggregate-display exists to stop exactly that. The feed
    merges at render time instead, which costs a few queries and buys the
    absence of the one table nobody could then resist totalling.
    """

    def test_no_model_records_activity(self):
        from django.apps import apps

        names = {m.__name__.lower() for m in apps.get_models()}
        for forbidden in ("activity", "event", "feeditem", "feedentry",
                          "timeline", "story", "auditlog", "actionlog"):
            self.assertNotIn(forbidden, names)

    def test_the_feed_item_wrapper_is_not_a_model(self):
        from django.db import models

        from site_app.views import FeedItem

        self.assertFalse(issubclass(FeedItem, models.Model))

    def test_it_sorts_on_facts_about_the_thing(self):
        """band, when and recency. Nothing about the person, which is the
        whole ordering contract."""
        from site_app.views import FeedItem

        self.assertEqual(set(FeedItem.__slots__),
                         {"kind", "obj", "band", "when", "recency"})


class TheTabsReachTheNewKinds(FeedBase):
    def test_there_is_a_days_tab(self):
        """A filter with no way to reach it is a filter nobody uses."""
        self.sign_in(self.hannah.user)
        self.assertContains(self.client.get("/board/"), 'href="/community/?show=days"')

    def test_every_tab_leads_somewhere_the_view_understands(self):
        """The tabs and the view's branches drifting apart is how a tab
        starts silently showing everything."""
        import re

        self.sign_in(self.hannah.user)
        body = self.client.get("/board/").content.decode()
        offered = set(re.findall(r'\?show=(\w+)', body))

        import inspect

        from site_app import views

        source = inspect.getsource(views._feed_for)
        for name in offered:
            with self.subTest(tab=name):
                self.assertIn(f'show == "{name}"', source)
