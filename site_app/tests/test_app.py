"""The member application, end to end.

The tests that matter most are the ones asserting what the app will NOT do:
serve another organization's postings, or let anything depend on what a member
has given.
"""

import re
from decimal import Decimal

from django import forms
from django.contrib.auth.models import User
from django.conf import settings
from django.test import TestCase, override_settings

from .helpers import SignedIn

from site_app.forms import ContactForm
from site_app.models import Claim, Contribution, Member, Posting, Organization
from site_app.tenancy import set_tenant, tenant_context


class AppBase(SignedIn, TestCase):
    def setUp(self):
        self.alpha = Organization.objects.create(slug="alpha", name="Alpha Mutual Aid")
        self.beta = Organization.objects.create(slug="beta", name="Beta Mutual Aid")

        self.ada_user = User.objects.create_user("ada", password="dugnad-test-pw")
        self.bo_user = User.objects.create_user("bo", password="dugnad-test-pw")

        with tenant_context(self.alpha):
            self.ada = Member.objects.create(
                organization=self.alpha, display_name="Ada", user=self.ada_user)
            self.other_alpha = Member.objects.create(
                organization=self.alpha, display_name="Ola")
            self.a_offering = Posting.objects.create(
                organization=self.alpha, member=self.other_alpha,
                description="Two crates of potatoes.")

        with tenant_context(self.beta):
            self.bo = Member.objects.create(
                organization=self.beta, display_name="Bo", user=self.bo_user)
            self.b_offering = Posting.objects.create(
                organization=self.beta, member=self.bo,
                description="Ladder, free to borrow.")

        set_tenant(None)

    def tearDown(self):
        set_tenant(None)


class SignIn(AppBase):
    def test_a_member_can_sign_in_and_is_sent_to_the_second_factor(self):
        """Signing in proves one factor, and lands on proving the second.

        The login view redirects to /board/; RequireMFAMiddleware bounces
        that to /mfa/setup/ because this account has not enrolled. Following the
        chain is the honest assertion.
        """
        response = self.client.post(
            "/login/", {"username": "ada", "password": "dugnad-test-pw"}, follow=True)
        self.assertEqual(response.redirect_chain[-1][0], "/mfa/setup/")

    def test_a_wrong_password_does_not_sign_in(self):
        response = self.client.post(
            "/login/", {"username": "ada", "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "do not match")

    def test_offerings_require_signing_in(self):
        response = self.client.get("/board/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])


class Isolation(AppBase):
    def test_a_member_sees_only_their_own_organizations_postings(self):
        self.sign_in(self.ada_user)
        response = self.client.get("/board/")
        self.assertContains(response, "potatoes")
        self.assertNotContains(response, "Ladder")

    def test_the_other_organization_sees_the_mirror_image(self):
        self.sign_in(self.bo_user)
        response = self.client.get("/board/")
        self.assertContains(response, "Ladder")
        self.assertNotContains(response, "potatoes")

    def test_another_organizations_offering_cannot_be_claimed_by_url(self):
        # Guessing the id is not enough: RLS makes the row unreachable.
        self.sign_in(self.ada_user)
        response = self.client.post(f"/board/{self.b_offering.id}/claim/")
        self.assertEqual(response.status_code, 404)


class Postings(AppBase):
    def test_a_member_can_put_something_up(self):
        self.sign_in(self.ada_user)
        response = self.client.post("/board/new/", {
            "kind": "offer",
            "description": "Half a Saturday and a working truck.",
            "hours_cap": "4",
        })
        self.assertRedirects(response, "/board/")
        with tenant_context(self.alpha):
            o = Posting.objects.get(member=self.ada)
            self.assertEqual(o.hours_cap, 4)

    def test_the_form_offers_no_category_or_rate(self):
        """no-catalog, as a UI test.

        Checks the CONTROLS, not the prose. An earlier version grepped the whole
        page for "category" and failed on the lede, which says there is no
        category to pick — which would have forced a choice between honest copy
        and a green build.
        """
        from site_app.forms import PostingForm

        # Two additions, both allowed, for the same reason: neither describes
        # the WORK. needed_by is a fact about the need. project is a pointer to
        # one specific, member-written, organization-scoped effort.
        #
        # project is the one worth arguing about, because it renders as a
        # dropdown and a dropdown is what a catalog looks like. The difference
        # is that a catalog is a fixed vocabulary of service TYPES — "Plumbing",
        # "Childcare" — which makes two postings comparable and comparable work
        # has an ascertainable value. Project names are prose somebody typed
        # about one job, and two postings under "Repairing homes on the east
        # side" are not comparable as services. The safeguard is that no
        # project list is ever shipped with the software; if one starts looking
        # like a taxonomy, that is the drift to catch.
        self.assertEqual(set(PostingForm().fields),
                         {"kind", "description", "project", "needed_by", "hours_cap"})

        self.sign_in(self.ada_user)
        body = self.client.get("/board/new/").content.decode().lower()

        # This assertion used to be `assertNotIn("<select", body)` — no
        # dropdowns at all. That was a good proxy while it held, and the
        # project picker breaks it, so it is replaced with the thing it was
        # standing in for rather than loosened.
        #
        # A catalog is a fixed vocabulary SHIPPED WITH THE SOFTWARE. So: the
        # only dropdown may be project, and its options must come from rows
        # somebody wrote, never from choices= in code. A ModelChoiceField reads
        # the database; a ChoiceField carries its vocabulary in the source. The
        # category field this test exists to prevent would be the second kind.
        selects = set(re.findall(r'<select[^>]*name="([^"]+)"', body))
        self.assertEqual(selects, {"project"}, "an unexpected dropdown appeared")
        self.assertIsInstance(PostingForm().fields["project"],
                              forms.ModelChoiceField)

        # Nothing on the model may carry a vocabulary except kind, which is a
        # direction — offer or need — and not a description of the work.
        with_choices = {f.name for f in Posting._meta.get_fields()
                        if getattr(f, "choices", None)}
        self.assertEqual(with_choices, {"kind"})

        posted = set(re.findall(
            r'<(?:input|textarea|select)[^>]*name="([^"]+)"', body))
        self.assertEqual(posted - {"csrfmiddlewaretoken"},
                         {"kind", "description", "project", "needed_by", "hours_cap"})

    def test_only_the_offerer_can_close_it(self):
        self.sign_in(self.ada_user)
        response = self.client.post(f"/board/{self.a_offering.id}/close/")
        self.assertEqual(response.status_code, 403)
        with tenant_context(self.alpha):
            self.a_offering.refresh_from_db()
            self.assertTrue(self.a_offering.open)


class ClaimingIsUngated(AppBase):
    def test_a_member_with_no_contributions_can_claim(self):
        """The load-bearing behaviour of the whole system."""
        self.sign_in(self.ada_user)
        with tenant_context(self.alpha):
            self.assertEqual(Contribution.objects.filter(member=self.ada).count(), 0)

        response = self.client.post(f"/board/{self.a_offering.id}/claim/")
        self.assertEqual(response.status_code, 302)

        with tenant_context(self.alpha):
            self.assertEqual(Claim.objects.filter(member=self.ada).count(), 1)

    def test_the_offerings_page_never_shows_what_anyone_has_given(self):
        # If a total ever appears next to a name, the log has become a score.
        self.sign_in(self.ada_user)
        body = self.client.get("/board/").content.decode().lower()
        for forbidden in ("hours given:", "total hours", "contributed ", "balance"):
            self.assertNotIn(forbidden, body)


class Ledger(AppBase):
    def test_recorded_hours_appear_in_the_log(self):
        self.sign_in(self.ada_user)
        response = self.client.post(f"/board/{self.a_offering.id}/hours/", {
            "hours": "2.5", "note": "Dug and washed them.",
        })
        self.assertRedirects(response, "/ledger/")

        body = self.client.get("/ledger/").content.decode()
        self.assertIn("2.50", body)
        self.assertIn("Dug and washed them.", body)

    def test_the_ledger_shows_no_totals(self):
        self.sign_in(self.ada_user)
        self.client.post(f"/board/{self.a_offering.id}/hours/",
                         {"hours": "2.5", "note": ""})
        self.client.post(f"/board/{self.a_offering.id}/hours/",
                         {"hours": "1.5", "note": ""})

        # Assert on the table DATA, not the page prose - the lede legitimately
        # says "there are no totals here".
        body = self.client.get("/ledger/").content.decode()
        tbody = re.search(r"<tbody>(.*?)</tbody>", body, re.S).group(1)
        figures = re.findall(r'<td class="hrs">([\d.]+)</td>', tbody)
        self.assertEqual(sorted(figures), ["1.50", "2.50"])
        # 2.5 + 1.5 = 4.00 is computed nowhere and rendered nowhere.
        self.assertNotIn("4.00", tbody)

    def test_the_ledger_is_scoped_to_the_organization(self):
        with tenant_context(self.beta):
            from site_app import services
            services.record_contribution(
                member=self.bo, posting=self.b_offering, hours=Decimal("9"))

        self.sign_in(self.ada_user)
        # Scoped to the ledger TABLE, not the whole document. Scanning the
        # page for "Bo" passed until the nav label became "Board", which
        # contains it — a two-letter substring against a full HTML response
        # tests the surrounding copy as much as the isolation. The leak, if
        # there were one, would be a row.
        import re

        body = self.client.get("/ledger/").content.decode()
        rows = re.search(r"<tbody>(.*?)</tbody>", body, re.S).group(1)

        self.assertNotIn("Bo", rows)
        self.assertNotIn("9.00", rows)
        # And the isolation itself, independent of any rendering.
        with tenant_context(self.alpha):
            from site_app.models import Contribution
            self.assertEqual(Contribution.objects.count(), 0)


class WayIn(SignedIn, TestCase):
    """The front page must offer a way to sign in.

    It did not: a member arriving at dugnadsand.org had to already know to type
    /login/. The link is small on purpose - this is a public page about an idea,
    not a product login - but it has to exist.
    """

    def test_the_landing_page_links_to_sign_in(self):
        body = self.client.get("/").content.decode()
        self.assertIn('href="/login/"', body)
        self.assertIn("Sign in", body)

    def test_the_attestation_page_links_to_sign_in_too(self):
        body = self.client.get("/attestation/").content.decode()
        self.assertIn('href="/login/"', body)

    def test_a_signed_in_member_is_pointed_at_the_app_instead(self):
        from django.contrib.auth.models import User

        from site_app.models import Member, Organization
        from site_app.tenancy import set_tenant, tenant_context

        org = Organization.objects.create(slug="wayin", name="Way In")
        user = User.objects.create_user("wi", password="dugnad-test-pw")
        with tenant_context(org):
            Member.objects.create(organization=org, display_name="Wi", user=user)
        set_tenant(None)

        self.sign_in(user)
        body = self.client.get("/").content.decode()
        self.assertIn('href="/board/"', body)
        self.assertNotIn("Sign in", body)


class Needs(AppBase):
    """Asking must cost nothing and prove nothing.

    A need is the direction mutual aid actually runs in most of the time, and
    it is also where gating would creep back: it is very natural to rank
    requests by who has given most, or to let people ask only once they have
    contributed. Neither may exist.
    """

    def post_need(self, description="A ride to the clinic on Thursday."):
        self.sign_in(self.ada_user)
        return self.client.post("/board/new/", {
            "kind": "need", "description": description, "hours_cap": "2"})

    def test_a_member_can_ask_for_something(self):
        from site_app.models import Posting

        response = self.post_need()
        self.assertRedirects(response, "/board/")
        with tenant_context(self.alpha):
            need = Posting.objects.get(kind=Posting.NEED)
            self.assertEqual(need.member, self.ada)
            self.assertTrue(need.is_need)

    def test_somebody_who_has_given_nothing_can_still_ask(self):
        """The whole point, restated for the asking direction."""
        from site_app.models import Contribution, Posting

        with tenant_context(self.alpha):
            self.assertEqual(Contribution.objects.filter(member=self.ada).count(), 0)
        self.post_need()
        with tenant_context(self.alpha):
            self.assertEqual(Posting.objects.filter(kind=Posting.NEED).count(), 1)

    def test_the_board_shows_needs_and_offers_separately(self):
        self.post_need("A ride to the clinic on Thursday.")
        body = self.client.get("/board/").content.decode()
        self.assertIn("People are asking for", body)
        self.assertIn("People are offering", body)
        self.assertIn("ride to the clinic", body)
        self.assertIn("potatoes", body)

    def test_undated_needs_keep_recency_order(self):
        """Ranking requests by contribution is gating wearing a sort order.

        Needs with a date sort by that date (see test_matching.WhenItIsNeeded);
        needs without one fall back to recency, because there is nothing else
        about them to sort on that is not about the person who asked.
        """
        from site_app.models import Posting

        self.sign_in(self.ada_user)
        for text in ("first need", "second need"):
            self.client.post("/board/new/",
                             {"kind": "need", "description": text, "hours_cap": ""})

        body = self.client.get("/board/").content.decode()
        self.assertLess(body.index("second need"), body.index("first need"))

    def test_somebody_can_take_on_a_need(self):
        from site_app.models import Claim, Posting

        self.post_need()
        with tenant_context(self.alpha):
            need = Posting.objects.get(kind=Posting.NEED)

        # A different member steps forward.
        other = User.objects.create_user("ola", password="dugnad-test-pw")
        with tenant_context(self.alpha):
            self.other_alpha.user = other
            self.other_alpha.save()

        self.sign_in(other)
        self.assertEqual(self.client.post(f"/board/{need.id}/claim/").status_code, 302)
        with tenant_context(self.alpha):
            self.assertEqual(Claim.objects.filter(posting=need).count(), 1)

    def test_the_board_shows_who_is_on_a_posting(self):
        from site_app.models import Posting

        self.post_need()
        with tenant_context(self.alpha):
            need = Posting.objects.get(kind=Posting.NEED)
        other = User.objects.create_user("ola", password="dugnad-test-pw")
        with tenant_context(self.alpha):
            self.other_alpha.user = other
            self.other_alpha.save()

        self.sign_in(other)
        self.client.post(f"/board/{need.id}/claim/")
        body = self.client.get("/board/").content.decode()
        self.assertIn("On it:", body)
        self.assertIn("Ola", body)

    def test_the_form_still_offers_no_category(self):
        # kind is a direction, not a taxonomy: exactly two choices, both fixed.
        from site_app.forms import PostingForm

        choices = dict(PostingForm().fields["kind"].choices)
        self.assertEqual(set(choices), {"offer", "need"})
        # Two additions, both allowed, for the same reason: neither describes
        # the WORK. needed_by is a fact about the need. project is a pointer to
        # one specific, member-written, organization-scoped effort.
        #
        # project is the one worth arguing about, because it renders as a
        # dropdown and a dropdown is what a catalog looks like. The difference
        # is that a catalog is a fixed vocabulary of service TYPES — "Plumbing",
        # "Childcare" — which makes two postings comparable and comparable work
        # has an ascertainable value. Project names are prose somebody typed
        # about one job, and two postings under "Repairing homes on the east
        # side" are not comparable as services. The safeguard is that no
        # project list is ever shipped with the software; if one starts looking
        # like a taxonomy, that is the drift to catch.
        self.assertEqual(set(PostingForm().fields),
                         {"kind", "description", "project", "needed_by", "hours_cap"})


class ThePublicCopyStaysTrue(SignedIn, TestCase):
    """The front page makes claims to strangers. They have to still hold.

    "We keep one record: hours" was true when it was written and stopped being
    true when material arrived — and nothing caught it, because no test reads
    the page a nonprofit actually reads. These do, at the level of the CLAIM
    rather than the wording, so honest rewrites stay cheap.
    """

    def copy(self, url):
        """Rendered text with whitespace collapsed.

        Assert the CLAIM, never the line wrapping. The first version of these
        looked for "not legal advice" and failed because the sentence broke
        across two lines in the template — a test that fails on reflow makes
        every honest edit look like a regression.
        """
        import re

        return re.sub(r"\s+", " ", self.client.get(url).content.decode()).lower()

    def test_the_front_page_does_not_claim_a_single_record(self):
        body = self.copy("/")
        for stale in ("one record", "the whole ledger"):
            self.assertNotIn(stale, body)

    def test_the_front_page_says_nothing_is_valued(self):
        self.assertIn("never what it was worth", self.copy("/"))

    def test_the_front_page_mentions_material_at_all(self):
        """Material is a first-class part of this now. A page that only
        describes hours undersells it to exactly the people it is for."""
        body = self.copy("/")
        self.assertTrue(any(w in body for w in ("board-feet", "shingles", "material")))

    def test_how_it_works_is_public_and_needs_no_account(self):
        response = self.client.get("/how-it-works/")
        self.assertEqual(response.status_code, 200)

    def test_how_it_works_says_it_is_not_legal_advice(self):
        """It describes tax-adjacent behaviour to nonprofit boards. The
        disclaimer is not decoration."""
        # The CLAIM, not its phrasing. These pages get rewritten; the three
        # things the disclaimer has to establish do not change.
        body = self.copy("/how-it-works/")
        self.assertIn("not a legal attestation", body)
        self.assertIn("not legal advice", body)
        self.assertIn("not a tax opinion", body)
        self.assertIn("counsel", body)

    def test_how_it_works_is_reachable_from_the_public_pages(self):
        for page in ("/", "/attestation/"):
            self.assertIn("/how-it-works/",
                          self.client.get(page).content.decode(), page)

    def test_how_it_works_points_at_the_proof_rather_than_asserting_it(self):
        body = self.client.get("/how-it-works/").content.decode()
        self.assertIn("/attestation/", body)

    def test_the_claims_it_names_are_claims_the_manifest_actually_makes(self):
        """Naming a check the manifest does not carry would be inventing
        assurance in public."""
        from policy.attest import load_manifest

        declared = {i["id"] for i in load_manifest()["invariant"]}
        body = self.client.get("/how-it-works/").content.decode()

        named = {line.split("</td>")[0].split(">")[-1]
                 for line in body.splitlines() if 'class="id"' in line}
        self.assertTrue(named)
        self.assertTrue(named <= declared, f"not in the manifest: {named - declared}")


class TheTaglineIsOnThePage(SignedIn, TestCase):
    """It was the tagline from the first commit and lived only in <title>.

    Which is to say the browser tab was the one place anybody could read it —
    exactly the kind of thing that goes missing without anyone deciding it
    should. Now it is on the page, and this keeps it there.
    """

    def test_the_front_page_carries_it_where_a_reader_can_see_it(self):
        import re

        body = self.client.get("/").content.decode()
        visible = re.sub(r"<head>.*?</head>", "", body, flags=re.S)
        visible = re.sub(r"\s+", " ", visible)
        self.assertIn("The work we do together", visible)

    def test_it_still_matches_the_brand(self):
        """If the tagline changes in brand.json and not on the page, one of
        the two is lying about what this is called."""
        import json
        from pathlib import Path

        brand = json.loads(
            (Path(__file__).resolve().parents[2] / "brand.json").read_text())
        body = self.client.get("/").content.decode()
        self.assertIn(brand["tagline"], body)


class TheNavigationStaysGrouped(SignedIn, TestCase):
    """The nav decayed to ten flat items, ordered by when things were built.

    That is the default outcome: every feature adds a link, nobody removes
    one, and a member ends up reading a list of features instead of seeing
    where things live. These tests hold the shape — three subject systems,
    two surfaces across them, and personal things folded away.
    """

    AREAS = ["/board/", "/pairings/", "/projects/", "/warehouse/", "/ledger/"]

    def setUp(self):
        self.org = Organization.objects.create(slug="alpha", name="Alpha")
        self.user = User.objects.create_user(
            "ada", email="ada@example.test", password="dugnad-test-pw")
        with tenant_context(self.org):
            Member.objects.create(organization=self.org, display_name="Ada",
                                  user=self.user)
        self.sign_in(self.user)

    def nav(self):
        import re

        body = self.client.get("/board/").content.decode()
        return re.search(r'<nav class="areas">(.*?)</nav>', body, re.S).group(1)

    def test_the_top_row_holds_the_areas_and_only_the_areas(self):
        import re

        hrefs = re.findall(r'href="([^"]+)"', self.nav())
        self.assertEqual(hrefs, self.AREAS)

    def test_personal_things_are_folded_away_rather_than_in_the_row(self):
        """Kept, Password and Sign out are yours, not the organization's."""
        nav = self.nav()
        for personal in ("/pinned/", "/password/", "/logout/"):
            self.assertNotIn(personal, nav)

    def test_they_are_still_reachable(self):
        """Folded away is not the same as gone, and the difference is the
        whole risk of tidying a menu."""
        body = self.client.get("/board/").content.decode()
        for personal in ("/pinned/", "/password/", "/logout/"):
            self.assertIn(personal, body)

    def test_every_area_link_actually_resolves(self):
        """A nav entry pointing at a 404 is worse than no nav entry."""
        for path in self.AREAS:
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_the_current_area_is_marked_on_each_of_its_pages(self):
        for path, section in (("/board/", "Board"), ("/warehouse/", "On hand"),
                              ("/projects/", "Ongoing"), ("/ledger/", "Ledger")):
            body = self.client.get(path).content.decode()
            self.assertRegex(body, rf'aria-current="page"[^>]*>{section}<',
                             msg=path)

    def test_the_warehouse_pages_carry_one_strip_between_them(self):
        """Two pages of one system should say so, rather than being two
        unrelated destinations that happen to share a word."""
        for path in ("/warehouse/", "/manifests/"):
            body = self.client.get(path).content.decode()
            self.assertIn('class="subnav"', body, path)
            self.assertIn("/manifests/", body, path)
            self.assertIn("/warehouse/", body, path)


class NoTemplateCommentReachesThePage(SignedIn, TestCase):
    """Django's {# #} is SINGLE-LINE ONLY. A multi-line one is not a comment.

    It renders as literal text, and it shipped: a three-line note about how the
    navigation is ordered sat visible in the nav bar of every signed-in page
    from 7832bfe until somebody read it on screen. Nothing caught it, because
    every test asserted what SHOULD be on a page and none asserted what should
    not.

    This checks the rendered output rather than the source, because a
    single-line {# #} in a template is correct and common — the defect is only
    ever visible after rendering.
    """

    PUBLIC = ["/", "/how-it-works/", "/policy/", "/virtual-warehouse/",
              "/attestation/", "/login/"]
    MEMBER = ["/board/", "/board/new/", "/projects/", "/warehouse/",
              "/manifests/", "/pairings/", "/pinned/", "/you/", "/notices/",
              "/ledger/", "/password/"]

    def setUp(self):
        self.org = Organization.objects.create(slug="alpha", name="Alpha")
        self.user = User.objects.create_user(
            "ada", email="ada@example.test", password="dugnad-test-pw")
        with tenant_context(self.org):
            Member.objects.create(organization=self.org, display_name="Ada",
                                  user=self.user)

    def leaks(self, paths):
        found = []
        for path in paths:
            body = self.client.get(path).content.decode()
            if "{#" in body or "{%" in body:
                found.append(path)
        return found

    def test_no_public_page_shows_template_syntax(self):
        self.assertEqual(self.leaks(self.PUBLIC), [])

    def test_no_member_page_shows_template_syntax(self):
        self.sign_in(self.user)
        self.assertEqual(self.leaks(self.MEMBER), [])

    def test_the_nav_itself_is_clean(self):
        """Where it actually happened, asserted on its own so a future failure
        names the nav rather than a list of eleven pages."""
        import re

        self.sign_in(self.user)
        body = self.client.get("/board/").content.decode()
        header = re.search(r"<header.*?</header>", body, re.S).group(0)

        self.assertNotIn("{#", header)
        self.assertNotIn("{%", header)


@override_settings(TEMPLATES=[{
    **settings.TEMPLATES[0],
    "OPTIONS": {**settings.TEMPLATES[0]["OPTIONS"],
                "string_if_invalid": "!!MISSING(%s)!!"},
}])
class NoTemplateVariableSilentlyFails(SignedIn, TestCase):
    """Django resolves a missing template variable to the empty string.

    So {{ e.offering.description }} rendered as nothing for months after
    Offering was renamed to Posting in 0006 — the ledger's "Toward" column was
    blank on every row and the page looked fine. The record-hours page had the
    same thing in its "For:" line.

    Nothing catches this by reading the code, because the template is valid and
    the view is correct. It only shows up by rendering with a marker in place
    of the silence.
    """

    PAGES = ["/board/", "/board/new/", "/projects/", "/warehouse/",
             "/manifests/", "/pairings/", "/pinned/", "/you/", "/notices/",
             "/ledger/", "/password/", "/members/"]

    def setUp(self):
        """EVERY LIST MUST HAVE A ROW IN IT.

        The first version of this created only a posting, and the guard passed
        with the original bug reinstated — the ledger's tables were empty, so
        the loop body never rendered and the missing variable inside it never
        had the chance to fail. A page that renders nothing proves nothing.
        """
        from datetime import date
        from decimal import Decimal

        from django.utils import timezone

        from site_app.models import (Manifest, MaterialGiven, MaterialNeed,
                                     Project, StockLine, Warehouse)
        from site_app.services import claim_posting, record_contribution
        from site_app.services_social import add_comment, toggle_pin

        self.org = Organization.objects.create(slug="alpha", name="Alpha")
        self.user = User.objects.create_user(
            "ada", email="ada@example.test", password="dugnad-test-pw")
        other = User.objects.create_user(
            "ola", email="ola@example.test", password="dugnad-test-pw")

        with tenant_context(self.org):
            self.member = Member.objects.create(
                organization=self.org, display_name="Ada", user=self.user,
                is_organizer=True)
            ola = Member.objects.create(
                organization=self.org, display_name="Ola", user=other)

            project = Project.objects.create(
                organization=self.org, started_by=self.member,
                name="Repairing homes", description="Roofs.")
            self.posting = Posting.objects.create(
                organization=self.org, member=self.member, kind=Posting.NEED,
                project=project, description="A ride to the clinic.",
                needed_by=date.today())
            claim_posting(posting=self.posting, member=ola)
            record_contribution(posting=self.posting, member=ola,
                                hours=Decimal("3.00"), note="Drove.")
            add_comment(member=ola, project=project, body="I have a truck.")
            toggle_pin(member=self.member, posting=self.posting)

            need = MaterialNeed.objects.create(
                organization=self.org, project=project, description="Oak",
                quantity=Decimal("200.00"), unit="board-feet",
                added_by=self.member)
            MaterialGiven.objects.create(
                organization=self.org, need=need, member=ola,
                quantity=Decimal("50.00"), note="Dropped off.")

            barn = Warehouse.objects.create(
                organization=self.org, holder=self.member, name="North barn",
                address="Gate 4412")
            line = StockLine.objects.create(
                organization=self.org, warehouse=barn, description="Oak",
                quantity=Decimal("300.00"), unit="board-feet",
                confirmed_at=timezone.now(), confirmed_by=self.member)
            self.manifest = Manifest.objects.create(
                organization=self.org, stock_line=line,
                quantity=Decimal("20.00"), destination="Habitat build",
                sent_by=self.member)
            self.project, self.line, self.need = project, line, need

        self.sign_in(self.user)

    def missing(self, path):
        import re

        body = self.client.get(path, follow=True).content.decode()
        return sorted(set(re.findall(r"!!MISSING\(([^)]*)\)!!", body)))

    def test_no_app_page_renders_a_missing_variable(self):
        broken = {p: self.missing(p) for p in self.PAGES}
        broken = {p: v for p, v in broken.items() if v}
        self.assertEqual(broken, {})

    def test_every_page_actually_rendered_something(self):
        """The guard is worthless on an empty page, so this checks the pages
        it relies on are not empty."""
        for path, marker in (("/ledger/", "3.00"),
                             ("/warehouse/", "board-feet"),
                             ("/manifests/", "Habitat build"),
                             ("/projects/", "Repairing homes"),
                             ("/pinned/", "clinic")):
            self.assertIn(marker, self.client.get(path).content.decode(), path)

    def test_the_two_that_were_broken_stay_fixed(self):
        """Named on their own so a regression says which page, not which list."""
        self.assertEqual(self.missing("/ledger/"), [])
        self.assertEqual(
            self.missing(f"/board/{self.posting.id}/hours/"), [])
        self.assertEqual(self.missing(f"/projects/{self.project.id}/"), [])
        self.assertEqual(self.missing(f"/manifest/{self.manifest.id}/"), [])


class ACsrfFailureExplainsItself(TestCase):
    """Django's default is "CSRF verification failed. Request aborted."

    That is all a person gets, and it names a thing they have never heard of.
    Reachable now only for the authenticated forms — the contact form is
    exempt — but a member whose session went cold sees this too.
    """

    def post_without_token(self, cookies=None, path="/login/"):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        for name, value in (cookies or {}).items():
            client.cookies[name] = value
        return client.post(path, {"username": "ada", "password": "x"})

    @staticmethod
    def copy(response):
        """Whitespace collapsed — assert the sentence, never its wrapping."""
        return re.sub(r"\s+", " ", response.content.decode())

    def test_it_says_what_happened_without_jargon(self):
        body = self.copy(self.post_without_token())
        self.assertIn("didn't go through", body)
        self.assertNotIn("CSRF", body)
        self.assertNotIn("Request aborted", body)

    def test_a_browser_with_no_cookies_is_not_told_to_try_again(self):
        """If nothing came back, nothing will come back next time either."""
        body = self.copy(self.post_without_token())
        self.assertIn("won't help", body)

    def test_a_browser_that_sent_something_is_told_to_try_again(self):
        body = self.copy(self.post_without_token(
            cookies={"sessionid": "whatever"}))
        self.assertIn("trying once more", body)
        self.assertNotIn("won't help", body)


class TheContactFormNeedsNoCookie(TestCase):
    """A visitor with cookies blocked can now send a message.

    That is the whole point of the exemption: on 2026-08-11 somebody filled in
    the form, their browser returned nothing, and Django threw their message
    away. A token on an anonymous form protects nothing — the attack it
    prevents is riding a logged-in session — so it was costing real people
    for no security.

    What it incidentally did, keeping out bots that blind-POST without
    fetching the page, is now done by a signed timestamp that needs no cookie.
    """

    def client_without_cookies(self):
        from django.test import Client

        return Client(enforce_csrf_checks=True)

    def send(self, client=None, stamp=None, **over):
        data = {"name": "Ruth", "email": "ruth@example.test",
                "message": "We run a pantry in Pickens.",
                "t": ContactForm.stamp() if stamp is None else stamp}
        data.update(over)
        return (client or self.client_without_cookies()).post("/", data)

    def aged(self, seconds):
        """A stamp as though it were issued `seconds` ago."""
        import time

        from django.core import signing

        return signing.Signer(salt=ContactForm.STAMP_SALT).sign(
            str(int(time.time()) - seconds))

    def test_a_browser_with_no_cookies_can_send(self):
        from unittest.mock import patch

        with patch("kjerne_platform.email.send") as send:
            response = self.send(stamp=self.aged(30))

        self.assertEqual(response.status_code, 302)
        send.assert_called_once()

    def test_the_message_reaches_the_inbox_intact(self):
        from unittest.mock import patch

        with patch("kjerne_platform.email.send") as send:
            self.send(stamp=self.aged(30))

        body = send.call_args.kwargs["body"]
        self.assertIn("pantry in Pickens", body)
        self.assertIn("ruth@example.test", body)

    def test_a_blind_post_with_no_stamp_is_refused(self):
        """What CSRF was incidentally doing, without the cookie."""
        from unittest.mock import patch

        with patch("kjerne_platform.email.send") as send:
            response = self.send(stamp="")

        self.assertEqual(response.status_code, 200)   # redisplayed, not sent
        send.assert_not_called()

    def test_a_forged_stamp_is_refused(self):
        from unittest.mock import patch

        with patch("kjerne_platform.email.send") as send:
            self.send(stamp="1754900000:forged")
        send.assert_not_called()

    def test_a_stamp_from_yesterday_is_refused(self):
        from unittest.mock import patch

        with patch("kjerne_platform.email.send") as send:
            self.send(stamp=self.aged(60 * 60 * 25))
        send.assert_not_called()

    def test_an_instant_submission_is_refused(self):
        """Nobody types a name, an address and a sentence in under a second."""
        from unittest.mock import patch

        with patch("kjerne_platform.email.send") as send:
            self.send(stamp=self.aged(0))
        send.assert_not_called()

    def test_too_fast_and_too_old_read_identically(self):
        """Telling a script it was too quick tells it what to change."""
        fast = self.copy_text(self.send(stamp=self.aged(0)))
        stale = self.copy_text(self.send(stamp=self.aged(60 * 60 * 25)))
        self.assertIn("went stale", fast)
        self.assertNotIn("too quick", fast)
        self.assertNotIn("too fast", fast)
        self.assertTrue(stale)

    def test_the_honeypot_still_catches_a_bot(self):
        from unittest.mock import patch

        with patch("kjerne_platform.email.send") as send:
            self.send(stamp=self.aged(30), website="http://spam.example")
        send.assert_not_called()

    def test_a_rejected_form_comes_back_with_a_fresh_stamp(self):
        """Otherwise fixing a typo is judged on when the FIRST page was drawn,
        and the anti-spam check becomes its own dead end."""
        import re

        response = self.send(stamp=self.aged(30), email="not-an-address")
        body = response.content.decode()
        stamp = re.search(r'name="t" value="([^"]+)"', body).group(1)

        from django.core import signing
        import time

        issued = int(signing.Signer(salt=ContactForm.STAMP_SALT).unsign(stamp))
        self.assertLess(int(time.time()) - issued, 5)

    def test_the_page_still_renders_a_stamp_for_a_first_visit(self):
        import re

        body = self.client.get("/").content.decode()
        self.assertRegex(body, r'name="t" value="\d+:')

    def test_authenticated_forms_still_require_csrf(self):
        """The exemption is one anonymous view, not a posture."""
        from django.test import Client

        response = Client(enforce_csrf_checks=True).post(
            "/login/", {"username": "x", "password": "y"})
        self.assertEqual(response.status_code, 403)

    @staticmethod
    def copy_text(response):
        return re.sub(r"\s+", " ", response.content.decode())


class TheMigrationsMatchTheModels(TestCase):
    """Nothing catches migration drift except asking.

    Eight models carried hand-written migrations — written that way to avoid an
    interactive makemigrations prompt — that declared the RESOLVED related_name
    rather than the "%(class)ss" the models declare. Identical at runtime,
    identical in SQL, and enough to make `makemigrations --check` fail, which
    meant nobody could use it as a gate and the next person to run
    makemigrations would find a mystery migration mixed into their own.
    """

    def test_no_model_change_is_missing_a_migration(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        try:
            call_command("makemigrations", "--check", "--dry-run",
                         verbosity=1, stdout=out, stderr=out)
        except SystemExit:
            self.fail(
                "Models and migrations disagree. Run:\n"
                "    python3 manage.py makemigrations site_app\n"
                "and read what it wants before accepting it:\n\n"
                + out.getvalue())


class TheFooterReachesTheStatements(TestCase):
    """Four public pages, one footer, and the three documents worth finding.

    The commitments, the mechanics and the live proof are the whole argument
    for trusting this thing, and until now two of the three were reachable
    only from a page you had already found.
    """

    PUBLIC = ["/", "/how-it-works/", "/policy/", "/virtual-warehouse/",
              "/attestation/"]
    LINKS = ["/how-it-works/", "/policy/", "/virtual-warehouse/", "/attestation/"]

    def test_every_public_page_carries_them(self):
        for path in self.PUBLIC:
            body = self.client.get(path).content.decode()
            footer = re.search(r"<footer.*?</footer>", body, re.S)
            self.assertIsNotNone(footer, path)
            for link in self.LINKS:
                self.assertIn(link, footer.group(0), f"{link} missing from {path}")

    def test_the_links_resolve(self):
        """A footer link to a 404 is worse than no footer link."""
        for link in self.LINKS:
            self.assertEqual(self.client.get(link).status_code, 200, link)

    def test_the_styling_lives_where_all_four_pages_can_see_it(self):
        """Each page styles `body > footer` in its own <style> block, so the
        link styling in a page block would be three copies drifting apart.
        brand.css is the file all of them already load."""
        from pathlib import Path

        css = (Path(__file__).resolve().parents[2]
               / "static" / "css" / "brand.css").read_text()
        self.assertIn("body > footer a", css)


class TheWarehouseExplainer(TestCase):
    """A business decides whether to list a pallet before anybody gives them
    a login, so this has to be public and it has to be honest about limits."""

    def page(self):
        return re.sub(r"\s+", " ", self.client.get("/virtual-warehouse/").content.decode())

    def test_it_is_public(self):
        self.assertEqual(self.client.get("/virtual-warehouse/").status_code, 200)

    def test_the_diagram_is_real_markup_rather_than_a_picture(self):
        """Inline SVG inherits the palette, scales with the page, and its
        labels are text a screen reader can read."""
        page = self.page()
        self.assertIn("<svg", page)
        self.assertIn('role="img"', page)
        self.assertIn("aria-label", page)

    def test_the_example_manifest_is_marked_as_an_example(self):
        """A realistic document on a public page is a thing somebody will
        screenshot. It has to say what it is."""
        self.assertIn("not a real consignment", self.page())

    def test_the_example_carries_no_value_of_any_kind(self):
        page = self.page()
        self.assertNotIn("$", page)
        self.assertIn("States no value", page)

    def test_it_states_the_refusals_and_not_only_the_features(self):
        page = self.page()
        for required in ("does not enter the platform's custody",
                         "will not price anything",
                         "will not convert material into hours",
                         "will not classify material into types"):
            self.assertIn(required, page, required)

    def test_it_explains_why_there_are_no_material_categories(self):
        """The reasoning matters more than the rule: somebody will offer to
        add icons, and the page should already answer them."""
        page = self.page()
        self.assertIn("comparable", page)
        self.assertIn("board-feet to board-feet", page)

    def test_no_material_taxonomy_was_introduced_by_this_page(self):
        """A page about material is exactly where a category list creeps in."""
        from site_app.models import MaterialNeed, StockLine

        for model in (StockLine, MaterialNeed):
            with_choices = {f.name for f in model._meta.get_fields()
                            if getattr(f, "choices", None)}
            self.assertEqual(with_choices, set(), model.__name__)


class ThePublicRegisterStaysTechnical(TestCase):
    """SVEND-sponsored documentation, not a pitch.

    The public pages are read by a nonprofit board and by whoever advises them.
    They were written in a warm, second-person voice that reads as marketing
    and — more to the point — reads as generated. This holds the register.
    """

    PAGES = ["/", "/how-it-works/", "/policy/", "/virtual-warehouse/",
             "/attestation/"]

    def prose(self, path):
        """Rendered text with markup, style and script removed."""
        import html as html_mod

        body = self.client.get(path).content.decode()
        body = re.sub(r"<(script|style)\b.*?</\1>", " ", body, flags=re.S | re.I)
        return html_mod.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)))

    def test_no_public_page_addresses_the_reader_directly(self):
        """Second person is the register of a pitch. These are specifications
        about a system, and the reader is not a party to them."""
        offenders = {}
        for path in self.PAGES:
            hits = re.findall(r"\b(you|your|you're|yours|yourself)\b",
                              self.prose(path), re.I)
            if hits:
                offenders[path] = sorted(set(h.lower() for h in hits))
        self.assertEqual(offenders, {})

    def test_no_public_page_closes_a_paragraph_with_an_aphorism(self):
        """'…which is the whole design' and its relatives. They read as
        generated because they usually are."""
        offenders = [p for p in self.PAGES
                     if re.search(r"(?:which|and that) is (?:the|exactly|why|what|how)\b",
                                  self.prose(p), re.I)]
        self.assertEqual(offenders, [])

    def test_no_public_page_uses_the_word_ai(self):
        """Not what this is, and not how it should be described."""
        for path in self.PAGES:
            self.assertNotRegex(self.prose(path), r"\bAI\b")
