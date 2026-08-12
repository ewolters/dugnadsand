"""The acceptable use policy.

Nothing on that page is bound to a check — there is no executable test for
whether a posting is campaigning — which is exactly why it needs tests of a
different kind. What can be held is that it says so, and that the remedies it
names are the ones that actually exist.

A policy naming a remedy the software cannot perform is the same defect as a
commitment with no check behind it, arriving through a different page.
"""

import re

from django.test import TestCase


class ThePageExists(TestCase):
    def prose(self):
        import html as html_mod

        body = self.client.get("/acceptable-use/").content.decode()
        body = re.sub(r"<(script|style)\b.*?</\1>", " ", body, flags=re.S | re.I)
        return html_mod.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)))

    def test_it_is_public(self):
        """A rule nobody can read before joining is not a rule."""
        self.assertEqual(self.client.get("/acceptable-use/").status_code, 200)

    def test_it_is_linked_from_the_footer_of_the_public_pages(self):
        for path in ("/", "/policy/", "/how-it-works/"):
            self.assertIn("/acceptable-use/",
                          self.client.get(path).content.decode(), path)


class ItDoesNotBorrowTheManifestsAuthority(ThePageExists):
    """/policy/ can prove itself. This page cannot, and says so at the top."""

    def test_it_says_nothing_here_is_checkable(self):
        prose = self.prose()
        self.assertIn("no executable check", prose)
        self.assertIn("would read as enforcement while enforcing nothing", prose)

    def test_it_points_at_the_page_that_can_prove_itself(self):
        self.assertIn("/policy/",
                      self.client.get("/acceptable-use/").content.decode())

    def test_no_invariant_claims_to_enforce_conduct(self):
        """If one ever did, this page and the manifest would disagree about
        which of them is enforceable."""
        from policy.attest import load_manifest

        for invariant in load_manifest()["invariant"]:
            claim = invariant["claim"].lower()
            for word in ("conduct", "harass", "political", "campaign", "abuse"):
                self.assertNotIn(word, claim, invariant["id"])


class TheRemediesItNamesAreTheOnesThatExist(ThePageExists):
    """The defect this guards: a conduct policy that promises moderation the
    software cannot perform."""

    def test_it_admits_only_the_author_can_remove_a_posting(self):
        prose = self.prose()
        self.assertIn("removed by the member who wrote it and by nobody else",
                      prose)
        self.assertIn("no moderator account", prose)

    def test_only_the_author_really_can(self):
        """Asserted against the code, not against the sentence. If a moderator
        path is ever added, this fails and the page is wrong."""
        import inspect

        from site_app import views

        source = inspect.getsource(views.posting_close)
        self.assertIn("posting.member_id != member.id", source)

    def test_it_claims_no_automated_detection(self):
        prose = self.prose()
        self.assertIn("no automated detection", prose)
        self.assertIn("no reporting queue", prose)

    def test_it_promises_no_count_of_complaints(self):
        """A count of how often somebody was complained about is a score, and
        the system holds none."""
        self.assertIn("such a count is a score", self.prose())

    def test_removal_from_a_chapter_is_described_as_a_person_not_a_button(self):
        self.assertIn("performed by a person with administrative access",
                      self.prose())


class WhatItRestricts(ThePageExists):
    def test_it_restricts_campaigning_rather_than_opinion(self):
        """A rule against holding views would be neither enforceable nor
        desirable, and people in a chapter will disagree about a great deal."""
        prose = self.prose()
        self.assertIn("candidate for public office", prose)
        self.assertIn("narrower than a rule against holding or expressing views",
                      prose)

    def test_it_gives_the_second_basis_for_not_for_profits(self):
        self.assertIn("political campaign intervention", self.prose())

    def test_it_restricts_selling_consistently_with_the_manifest(self):
        prose = self.prose()
        self.assertIn("bought or sold", prose)
        self.assertIn("quote a price", prose)

    def test_it_disclaims_supervision_and_insurance(self):
        prose = self.prose()
        self.assertIn("carries no insurance for any member", prose)
        self.assertIn("verifies no competence", prose)
