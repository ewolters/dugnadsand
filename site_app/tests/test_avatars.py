"""A mark for a person, generated rather than uploaded.

The tests that matter are about what a mark cannot be. It cannot be a
photograph, because a face is judged and this system is built so nobody is.
It cannot carry anything a member typed, because it is inline markup. And it
cannot say anything about what somebody has given, because then it would be a
badge and a badge is a score you wear.
"""

import re

from django.contrib.auth.models import User
from django.test import TestCase

from site_app import avatars
from site_app.models import Member, Organization
from site_app.tenancy import tenant_context

from .helpers import SignedIn


class AvatarBase(SignedIn, TestCase):
    def setUp(self):
        self.org = Organization.objects.create(slug="alpha", name="Alpha")
        self.ada_user = User.objects.create_user(
            "ada", email="ada@example.test", password="dugnad-test-pw")
        with tenant_context(self.org):
            self.ada = Member.objects.create(
                organization=self.org, display_name="Ada", user=self.ada_user)
            self.ola = Member.objects.create(
                organization=self.org, display_name="Ola")


class NoPersonIsPhotographed(AvatarBase):
    """NARROWED, DELIBERATELY, WHEN THE IMPACT PACKET LANDED.

    This class used to assert that NO model anywhere stored an image and that
    no route contained the word "photo". That was the right shape while the
    only reason to want an image was a profile picture, and the decision it
    guarded is unchanged: a face next to a name reintroduces judgement of a
    PERSON through a channel no invariant covers, so members are drawn from
    their id and choose a colour.

    A photograph of a riverbank in an impact packet is a different object. It
    depicts the work; it is not anybody's representation in the application,
    it never appears beside a contribution, and the packet is the one thing
    this system sends to somebody who helped.

    So the rule is stated properly rather than approximated: an image may
    describe WORK and may never be the representation of a MEMBER. The blanket
    ban was a proxy for that, and a proxy that now forbids something Eric
    asked for is worse than the rule it stood in for.
    """

    #: The only model permitted to hold a file, and what it must hang off.
    IMAGE_BEARING = {"Photo": "project"}

    def test_no_model_outside_the_packet_stores_an_image(self):
        from django.apps import apps

        for model in apps.get_models():
            if not model.__module__.startswith("site_app"):
                continue
            for f in model._meta.get_fields():
                kind = getattr(f, "get_internal_type", lambda: "")()
                if kind not in ("ImageField", "FileField"):
                    continue
                self.assertIn(
                    model.__name__, self.IMAGE_BEARING,
                    f"{model.__name__}.{getattr(f, 'name', '')} stores a file; "
                    f"only {sorted(self.IMAGE_BEARING)} may")

    def test_an_image_hangs_off_the_work_never_off_a_person(self):
        """The line that matters. A Photo whose subject was a Member would be
        a profile picture with a different table name."""
        from django.apps import apps

        for name, subject in self.IMAGE_BEARING.items():
            model = apps.get_model("site_app", name)
            field = model._meta.get_field(subject)
            self.assertEqual(field.related_model.__name__, "Project",
                             f"{name}.{subject} no longer points at the work")

    def test_no_member_carries_an_image_of_any_kind(self):
        for f in Member._meta.get_fields():
            kind = getattr(f, "get_internal_type", lambda: "")()
            self.assertNotIn(kind, ("ImageField", "FileField"),
                             f"Member.{getattr(f, 'name', '')}")

    def test_no_route_sets_a_picture_of_a_member(self):
        from site_app import urls

        routes = " ".join(str(p.pattern) for p in urls.urlpatterns)
        for forbidden in ("avatar/set", "avatar/upload", "profile-photo",
                          "members/<uuid:member_id>/photo"):
            self.assertNotIn(forbidden, routes)

    def test_the_only_thing_stored_is_a_colour_name(self):
        names = {f.name for f in Member._meta.get_fields()}
        self.assertIn("avatar_colour", names)
        for forbidden in ("avatar", "photo", "picture", "image", "portrait"):
            self.assertNotIn(forbidden, names)


class TheMarkIsStable(AvatarBase):
    def test_the_same_person_draws_the_same_mark_every_time(self):
        with tenant_context(self.org):
            self.assertEqual(avatars.svg(self.ada), avatars.svg(self.ada))

    def test_two_people_do_not_draw_the_same_mark(self):
        with tenant_context(self.org):
            self.assertNotEqual(avatars.svg(self.ada), avatars.svg(self.ola))

    def test_it_is_derived_from_the_id_and_nothing_else(self):
        """Not from the display name — somebody correcting a typo in their own
        name should not become a different person on the page."""
        with tenant_context(self.org):
            before = avatars.svg(self.ada)
            self.ada.display_name = "Ada Henderson"
            self.ada.save(update_fields=["display_name"])
            self.assertEqual(avatars.svg(self.ada), before)

    def test_no_mark_is_ever_sparse_or_solid(self):
        """A floor and a ceiling, not a probability.

        Deciding per cell gives a distribution, so however the odds are tuned
        some ids still land on four scattered squares and others on a block.
        Both fail — one reads as noise, the other as a smudge — and neither
        reads as a particular person. Checked across many ids because the
        failure only ever showed up on a few.
        """
        import uuid

        widest = avatars.SIZE * avatars.SIZE
        for i in range(300):
            drawn = len(list(avatars.cells(uuid.UUID(int=i * 7919 + 13))))
            self.assertGreaterEqual(drawn, avatars.FEWEST + 4, i)
            self.assertLessEqual(drawn, widest - 2, i)

    def test_the_band_still_leaves_room_to_differ(self):
        """A floor that pinned every mark to one weight would trade noise for
        uniformity, which is the same failure from the other side."""
        import uuid

        seen = {len(list(avatars.cells(uuid.UUID(int=i * 7919 + 13))))
                for i in range(300)}
        self.assertGreater(len(seen), 3)

    def test_the_grid_is_mirrored(self):
        """What makes an arrangement of squares read as a thing rather than
        as noise."""
        filled = {(c, r) for c, r, _ in avatars.cells(self.ada.id)}
        for column, row in filled:
            self.assertIn((avatars.SIZE - 1 - column, row), filled)


class ChoosingAColour(AvatarBase):
    def test_everybody_has_one_before_choosing(self):
        with tenant_context(self.org):
            self.assertIn(avatars.colour_of(self.ola), avatars.PALETTE)

    def test_a_choice_is_honoured(self):
        with tenant_context(self.org):
            self.ada.avatar_colour = "rust"
            self.assertEqual(avatars.colour_of(self.ada), "rust")

    def test_the_pattern_does_not_change_with_the_colour(self):
        """Changing colour should not make somebody look like a different
        person."""
        with tenant_context(self.org):
            plain = re.sub(r'class="[^"]*"', "", avatars.svg(self.ada))
            self.ada.avatar_colour = "heather"
            self.assertEqual(re.sub(r'class="[^"]*"', "", avatars.svg(self.ada)),
                             plain)

    def test_a_colour_nobody_offers_falls_back_rather_than_breaking(self):
        with tenant_context(self.org):
            self.ada.avatar_colour = "chartreuse"
            self.assertIn(avatars.colour_of(self.ada), avatars.PALETTE)

    def test_the_page_saves_a_choice(self):
        self.sign_in(self.ada_user)
        self.client.post("/you/", {"colour": "slate"})
        with tenant_context(self.org):
            self.ada.refresh_from_db()
        self.assertEqual(self.ada.avatar_colour, "slate")

    def test_the_page_refuses_a_colour_it_does_not_offer(self):
        self.sign_in(self.ada_user)
        self.client.post("/you/", {"colour": "<script>"})
        with tenant_context(self.org):
            self.ada.refresh_from_db()
        self.assertEqual(self.ada.avatar_colour, "")

    def test_every_offered_colour_is_a_declared_brand_token(self):
        """The SVG carries no literal — colour arrives through a CSS custom
        property, so brand-lint still governs every value on the page."""
        import json
        from pathlib import Path

        brand = json.loads(
            (Path(__file__).resolve().parents[2] / "brand.json").read_text())
        for colour in avatars.PALETTE:
            self.assertIn(f"avatar_{colour}", brand["colors"], colour)


class TheMarkCarriesNothingElse(AvatarBase):
    def test_no_member_supplied_text_reaches_the_svg(self):
        with tenant_context(self.org):
            self.ada.display_name = '<script>alert(1)</script>'
            self.ada.avatar_colour = '" onload="x'
            html = avatars.svg(self.ada)

        self.assertNotIn("script", html)
        self.assertNotIn("onload", html)

    def test_it_emits_no_colour_literal(self):
        with tenant_context(self.org):
            html = avatars.svg(self.ada)
        self.assertNotIn("#", html)
        self.assertIn("currentColor", html)

    def test_it_says_nothing_about_what_anybody_has_given(self):
        """A mark that changed with contribution would be a badge, and a badge
        is a score you wear."""
        import inspect

        source = inspect.getsource(avatars)
        for forbidden in ("Contribution", "hours", "claim", "ledger"):
            self.assertNotIn(forbidden, source)

    def test_it_is_hidden_from_screen_readers_because_the_name_is_there(self):
        with tenant_context(self.org):
            self.assertIn('aria-hidden="true"', avatars.svg(self.ada))


class OnThePages(AvatarBase):
    def test_the_board_shows_a_mark_beside_whoever_posted(self):
        from site_app.models import Posting

        with tenant_context(self.org):
            Posting.objects.create(organization=self.org, member=self.ada,
                                   kind=Posting.NEED, description="A ride.")

        self.sign_in(self.ada_user)
        body = self.client.get("/board/").content.decode()
        self.assertIn('class="avatar av-', body)

    def test_your_own_page_renders_and_offers_every_colour(self):
        self.sign_in(self.ada_user)
        body = self.client.get("/you/").content.decode()
        for colour in avatars.PALETTE:
            self.assertIn(f'value="{colour}"', body)

    def test_your_page_offers_nothing_that_describes_you(self):
        """A profile saying what somebody is good at becomes a directory of
        people ranked by what they offer — the catalog problem, with faces."""
        self.sign_in(self.ada_user)
        body = self.client.get("/you/").content.decode().lower()
        for forbidden in ("bio", "about you", "skills", "headline", "tagline"):
            self.assertNotIn(forbidden, body)
