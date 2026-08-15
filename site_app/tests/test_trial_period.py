"""The trial period, and the two doors it closes.

Dugnadsand is running as a trial while whether it continues is decided.
Applications and blind requests are closed, for different reasons, and both
reasons are worth holding:

  APPLICATIONS, because admitting an organization is a commitment to operate
  the network for it, and that cannot honestly be made while the network's own
  future is open.

  BLIND REQUESTS, on arithmetic rather than policy. A request is shown to the
  mutual aid groups covering its area and to nobody else. With no group
  reading them it reaches nobody at all — so the form would take a name and a
  phone number from somebody having the worst week of their year and put them
  in a queue with no reader.

The second is the one that must not fail quietly. A closed door that still
accepts a POST is worse than an open one, because it looks like it worked.
"""

import re

from django.test import TestCase

from site_app import trial
from site_app.models import Application, Region, Request

from .test_requests import stamped


class TheDoorsAreShut(TestCase):
    def test_applications_are_closed(self):
        self.assertFalse(trial.APPLICATIONS_OPEN)

    def test_blind_requests_are_closed(self):
        self.assertFalse(trial.REQUESTS_OPEN)

    def test_the_date_is_declared_in_one_place(self):
        """Both pages read it. Two copies of a date is one wrong date."""
        self.assertEqual(trial.TRIAL_ENDS.year, 2026)
        self.assertEqual(trial.TRIAL_ENDS.month, 9)
        self.assertEqual(trial.TRIAL_ENDS.day, 30)


class Applying(TestCase):
    def test_the_url_still_answers(self):
        """Somebody following an old link deserves to be told what happened
        rather than to conclude the site is broken."""
        response = self.client.get("/apply/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Applications are closed")

    def test_it_names_the_date(self):
        self.assertContains(self.client.get("/apply/"), trial.ends_on())

    def prose(self, path):
        """Whitespace-normalised text. Templates wrap mid-sentence, so a
        phrase assertion against raw HTML fails on a line break rather than
        on the phrase being absent."""
        body = self.client.get(path).content.decode()
        body = re.sub(r"<(script|style)\b.*?</\1>", " ", body, flags=re.S | re.I)
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))

    def test_it_says_why_rather_than_only_that(self):
        """"Closed" with no reason reads as a network that failed. The
        reason is a decision in progress, and saying so is both accurate and
        the only version somebody could act on."""
        prose = self.prose("/apply/")
        self.assertIn("has not been decided", prose)
        self.assertIn("commitment to operate the network", prose)

    def test_it_says_existing_organizations_are_unaffected(self):
        self.assertIn("already admitted are unaffected", self.prose("/apply/"))

    def test_it_is_not_a_waiting_list(self):
        """A closed door that implies a queue collects hope instead of
        applications."""
        self.assertContains(self.client.get("/apply/"), "not a waiting list")

    def test_A_POST_CREATES_NOTHING(self):
        """The half that would matter. A page that hides its form and still
        accepts a POST is a closed door that opens when pushed."""
        response = self.client.post("/apply/", {
            "kind": "business", "legal_name": "Somebody LLC",
            "contact_name": "Dana", "email": "dana@example.test",
            "statement": "We wire things.", "agreed": "1"})

        self.assertEqual(Application.objects.count(), 0)
        self.assertContains(response, "Applications are closed")

    def test_nothing_still_links_to_it_as_though_it_were_open(self):
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1] / "templates"
        for path in root.rglob("*.html"):
            text = path.read_text()
            if 'href="/apply/"' in text:
                with self.subTest(page=path.name):
                    self.assertIn("closed", text.lower())


class AskingForHelp(TestCase):
    def setUp(self):
        self.region = Region.objects.create(slug="up", name="Upstate")

    def test_the_form_is_gone(self):
        body = self.client.get("/need-help/").content.decode()
        named = set(re.findall(r'<(?:input|textarea)[^>]*name="([^"]+)"', body))
        self.assertEqual(named - {"csrfmiddlewaretoken"}, set())

    def test_A_POST_RECORDS_NOTHING(self):
        """The one that must not fail quietly. Somebody holding the page open
        in a tab, or a script, must not be able to file a request nobody will
        read — and the details are the most sensitive this system takes."""
        self.client.post("/need-help/", stamped(
            need="A ride to dialysis.", reach_them="864 555 0102",
            asked_by="Marta", area="Travelers Rest"))
        self.assertEqual(Request.objects.count(), 0)

    def test_it_says_a_request_would_reach_nobody(self):
        """Accurate rather than soft. "Temporarily unavailable" would let
        somebody assume it is a glitch and try again tomorrow."""
        body = re.sub(r"\s+", " ", self.client.get("/need-help/").content.decode())
        self.assertIn("would reach nobody", body)
        self.assertIn("Not taking requests", body)

    def test_IT_POINTS_SOMEWHERE_REAL(self):
        """A page turning away somebody in trouble owes them a destination.
        Named services, not "search online"."""
        body = self.client.get("/need-help/").content.decode()
        # Hyphenated, as the page writes them — a number somebody has to dial
        # under stress reads better spaced out, and the test follows the page
        # rather than the page following the test.
        for expected in ("2-1-1", "9-8-8", "9-1-1"):
            with self.subTest(service=expected):
                self.assertIn(expected, body)

    def test_the_groups_directory_survives(self):
        """Closing the blind form does not close the page. Contacting a
        group directly needs nobody logged in, so it is unaffected."""
        self.assertContains(self.client.get("/need-help/"),
                            "Or contact a group directly")


class TheLocalServicesAreReal(TestCase):
    """A page turning somebody away owes them somewhere that answers.

    Nothing here can keep itself current — organizations move and numbers
    change — so the page carries the date it was checked and says plainly
    that 2-1-1 is the maintained directory this one is not. A list that looks
    authoritative while being three years stale sends somebody in trouble to
    a dead line, and they stop looking.
    """

    def body(self):
        return re.sub(r"\s+", " ", self.client.get("/need-help/").content.decode())

    def test_both_areas_are_named(self):
        body = self.body()
        self.assertIn("Greenville, South Carolina", body)
        self.assertIn("Asheville and Buncombe County", body)

    def test_the_areas_are_the_ones_this_chapter_covers(self):
        """Upstate SC and Western North Carolina. A list of services three
        states away is a gesture, not a destination."""
        areas = [area for area, _ in trial.LOCAL]
        self.assertTrue(any("Greenville" in a for a in areas))
        self.assertTrue(any("Asheville" in a for a in areas))

    def test_every_entry_carries_a_way_to_reach_it(self):
        for area, services in trial.LOCAL:
            for name, contact, what in services:
                with self.subTest(service=name):
                    self.assertTrue(contact.strip(), f"{name} has no contact")
                    self.assertRegex(contact, r"\(\d{3}\) \d{3}-\d{4}",
                                     f"{name}: no phone number in {contact!r}")
                    self.assertTrue(what.strip(), f"{name} says nothing")

    def test_each_area_covers_food_shelter_health_and_violence(self):
        """Not a list of four charities that happen to be nearby. The four
        things somebody arrives at this page needing."""
        for area, services in trial.LOCAL:
            joined = " ".join(f"{n} {w}" for n, _, w in services).lower()
            for need in ("food", "shelter", "medic|health|dental",
                         "domestic violence"):
                with self.subTest(area=area, need=need):
                    self.assertRegex(joined, need)

    def test_a_24_hour_route_exists_in_each_area(self):
        """The need that does not wait for opening hours."""
        for area, services in trial.LOCAL:
            joined = " ".join(c for _, c, _ in services).lower()
            with self.subTest(area=area):
                self.assertIn("24 hours", joined)

    def test_the_page_says_when_it_was_checked(self):
        self.assertIn(trial.checked_on(), self.body())

    def test_it_says_it_is_not_the_maintained_directory(self):
        """The honest limit. This page cannot keep itself current and 2-1-1
        can, so the reader is told which is which."""
        body = self.body()
        self.assertIn("2-1-1 is kept current and this page is not", body)

    def test_the_manna_entry_warns_about_the_old_address(self):
        """Search results, review sites and older guides still give the
        Swannanoa River Road warehouse, which flooded. Somebody driving there
        with nothing in the tank is the failure this sentence prevents."""
        body = self.body()
        self.assertIn("Mills River", body)
        self.assertIn("older listings still give", body)


class TheOneDoorLeftOpen(TestCase):
    """Interest is the only thing still being taken. It has to arrive.

    The closed-applications page pointed at /#contact while the form on the
    home page is id="say-hello", so the single route left open landed
    somebody at the top of the home page with no idea what to do next — a
    broken anchor being the quietest kind of broken.
    """

    def test_the_closed_page_links_an_anchor_that_exists(self):
        import re

        closed = self.client.get("/apply/").content.decode()
        anchors = set(re.findall(r'href="/#([a-z0-9-]+)"', closed))
        self.assertTrue(anchors, "the closed page offers no way to say anything")

        home = self.client.get("/").content.decode()
        for anchor in anchors:
            with self.subTest(anchor=anchor):
                self.assertIn(f'id="{anchor}"', home)

    def test_the_home_page_still_takes_a_message(self):
        home = self.client.get("/").content.decode()
        self.assertIn('name="message"', home)
