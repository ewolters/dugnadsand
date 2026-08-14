"""The page for somebody who needs help.

The last mile is not ours. A mutual aid group knows who on its street needs a
roof this month; it has no way of knowing a contractor forty miles away is
about to skip the shingles. This system does the second thing.

So the tests here are mostly about what the page REFUSES to be: no form, no
request, no record, and no account between a person in trouble and a phone
number.
"""

import re

from django.test import TestCase

from site_app.models import Organization, Region
from site_app.tenancy import set_tenant


class NeedHelpBase(TestCase):
    def setUp(self):
        self.chapter = Region.objects.create(slug="up", name="Upstate SC and WNC")
        self.listed = Organization.objects.create(
            slug="rivertown", name="Rivertown Mutual Aid", region=self.chapter,
            serves="Food, rides to appointments, and small home repairs.",
            public_contact="Call the church office, 555 0123, Tuesday to Thursday.")
        self.unlisted = Organization.objects.create(
            slug="quiet", name="Quiet Group", region=self.chapter)
        set_tenant(None)

    def tearDown(self):
        set_tenant(None)

    def page(self):
        return self.client.get("/need-help/").content.decode()

    def prose(self):
        import html as html_mod

        body = re.sub(r"<(script|style)\b.*?</\1>", " ", self.page(),
                      flags=re.S | re.I)
        return html_mod.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)))


class ItIsReachableByAnybody(NeedHelpBase):
    def test_no_account_is_needed(self):
        """An account between a person in trouble and a phone number is an
        obstacle, and it is the obstacle this page exists to remove."""
        self.assertEqual(self.client.get("/need-help/").status_code, 200)

    def test_it_is_linked_from_the_footer_of_every_public_page(self):
        for path in ("/", "/policy/", "/how-it-works/", "/chapters/"):
            self.assertIn("/need-help/", self.client.get(path).content.decode(), path)


class ItIsAnIntroductionAndNothingElse(NeedHelpBase):
    def test_the_form_asks_four_things_and_no_more(self):
        """Somebody in trouble is not filling in an intake assessment, and
        every extra question is a reason to close the tab."""
        import re

        body = self.page()
        named = set(re.findall(r'<(?:input|textarea|select)[^>]*name="([^"]+)"',
                               body))
        self.assertEqual(named - {"csrfmiddlewaretoken", "t", "website"},
                         {"need", "area", "asked_by", "reach_them", "region"})

    def test_it_says_exactly_who_sees_what(self):
        """Retargeted the moment the page grew a form.

        It asserted no record of a request exists here, which was true when
        the page was a directory and became false the same day. What has to
        hold now is narrower and more useful: who can see the need, who
        cannot see the contact, and that no outcome is recorded.
        """
        prose = self.prose()
        self.assertIn("and to nobody else", prose)
        self.assertIn("withheld until one group takes it up", prose)
        self.assertIn("Nothing records what was decided", prose)

    def test_it_says_the_group_decides(self):
        self.assertIn("groups below decide what they can do and for whom",
                      self.prose())


class OnlyGroupsThatChoseToBeListed(NeedHelpBase):
    def test_a_group_with_a_published_contact_appears(self):
        body = self.page()
        self.assertIn("Rivertown Mutual Aid", body)
        self.assertIn("555 0123", body)
        self.assertIn("rides to appointments", body)

    def test_a_group_that_published_nothing_does_not(self):
        """Blank means unlisted. Publishing a route to a group's door is a
        decision they make, not a default they discover."""
        self.assertNotIn("Quiet Group", self.page())

    def test_a_closed_organization_drops_off(self):
        Organization.objects.filter(pk=self.listed.pk).update(active=False)
        self.assertNotIn("Rivertown Mutual Aid", self.page())

    def test_groups_are_gathered_by_area(self):
        self.assertIn("Upstate SC and WNC", self.page())

    def test_with_nothing_listed_it_says_so_rather_than_pretending(self):
        Organization.objects.all().update(public_contact="")
        prose = self.prose()
        self.assertIn("No group has published a way to be contacted yet", prose)
        self.assertIn("better than a form that reaches nobody", prose)


class ThePolicySaysWhereTheSystemStops(NeedHelpBase):
    def prose_of(self, path):
        import html as html_mod

        body = re.sub(r"<(script|style)\b.*?</\1>", " ",
                      self.client.get(path).content.decode(), flags=re.S | re.I)
        return html_mod.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)))

    def test_it_states_that_no_beneficiary_is_a_party(self):
        prose = self.prose_of("/policy/")
        self.assertIn("does not reach the people who are helped", prose)
        self.assertIn("no beneficiary is a party to this system", prose)

    def test_it_explains_why_the_split_falls_where_it_does(self):
        self.assertIn("about to skip the shingles", self.prose_of("/policy/"))

    def test_it_points_at_the_page(self):
        self.assertIn("/need-help/", self.client.get("/policy/").content.decode())

    def test_the_repo_statement_says_the_same(self):
        from pathlib import Path

        text = (Path(__file__).resolve().parents[2] / "docs"
                / "policy-statement.md").read_text()
        self.assertIn("Where this system stops", text)
        self.assertIn("no beneficiary is a party to this system", text)
