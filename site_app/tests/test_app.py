"""The member application, end to end.

The tests that matter most are the ones asserting what the app will NOT do:
serve another organization's postings, or let anything depend on what a member
has given.
"""

import re
from decimal import Decimal

from django import forms
from django.contrib.auth.models import User
from django.test import TestCase

from .helpers import SignedIn

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
        body = self.client.get("/ledger/").content.decode()
        self.assertNotIn("Bo", body)
        self.assertNotIn("9.00", body)


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
