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

    def test_removal_names_what_it_does_and_what_it_does_not(self):
        """Retargeted the moment removal became a button.

        It asserted the page said removal was "performed by a person with
        administrative access", which was true when the only way to do it was
        a database edit. The property that has to survive is not who presses
        it but what it does: a reason is kept, and nothing is deleted.
        """
        prose = self.prose()
        self.assertIn("A reason is required and is kept", prose)
        self.assertIn("Nothing the organization wrote is deleted", prose)
        self.assertIn("Removal from a room is not erasure from the record", prose)

    def test_the_service_really_requires_a_reason(self):
        """Asserted against the code, not the sentence."""
        from site_app.services_applications import remove_from_chapter
        from site_app.models import Organization, Region

        region = Region.objects.create(slug="r", name="R")
        organization = Organization.objects.create(
            slug="o", name="O", region=region)
        from django.contrib.auth.models import User
        user = User.objects.create_user("officer", password="dugnad-test-pw")

        with self.assertRaises(ValueError):
            remove_from_chapter(organization=organization, region=region,
                                user=user, reason="   ")


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
