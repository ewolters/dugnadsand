"""The brand kit, pinned.

The kit went from a flat list of colours to a scale with a night axis when the
site became a social one. Both halves decay quietly if nothing holds them:

  A ONE-OFF VALUE is how the scale died the first time. The feed grew 10px
  cards, 2rem pills, 1rem bubbles and 12px panels over three sittings because
  each surface guessed instead of reaching for a token.

  A COMPONENT NAMING A NIGHT COLOUR is how the dark axis dies. Nothing outside
  brand.css may mention --brand-night-* or --brand-*-lift: the axis works by
  redefining the ordinary tokens, which is why 594 lines of app CSS flip
  without a component edit and why a surface built next week is dark-correct
  before anybody thinks about it. One component reaching for a night colour
  directly makes that surface permanently dark, in both grounds.

  brand.json AND brand.css both have to carry the same tokens: the linter
  reads the JSON, the browser reads the CSS, and they are generated apart.
"""

import json
import pathlib
import re

from django.test import TestCase

ROOT = pathlib.Path(__file__).resolve().parents[2]
BRAND_JSON = ROOT / "brand.json"
BRAND_CSS = ROOT / "static" / "css" / "brand.css"
APP_BASE = ROOT / "templates" / "app_base.html"


def app_css():
    """The style block in the app shell, which is where components live."""
    body = APP_BASE.read_text()
    return "\n".join(re.findall(r"<style>(.*?)</style>", body, re.S))


class TheScaleExists(TestCase):
    SCALE = ("radius_card", "radius_field", "radius_pill", "lift_1", "lift_2",
             "feed", "tap", "quick", "settle", "ease")

    def test_brand_json_declares_every_scale_token(self):
        tokens = json.loads(BRAND_JSON.read_text())["tokens"]
        for name in self.SCALE:
            self.assertIn(name, tokens)

    def test_brand_css_declares_the_same_ones(self):
        """Generated apart, so they drift apart unless something checks."""
        css = BRAND_CSS.read_text()
        for name in self.SCALE:
            self.assertIn(f"--brand-{name.replace('_', '-')}:", css)

    def test_the_feed_column_is_narrower_than_the_page(self):
        """A stream at document width reads as a spreadsheet of postings:
        the eye has to traverse to find the next name."""
        tokens = json.loads(BRAND_JSON.read_text())["tokens"]
        feed = float(tokens["feed"].rstrip("rem"))
        measure = float(tokens["measure"].rstrip("rem"))
        self.assertLess(feed, measure)

    def test_no_component_hardcodes_a_corner_radius(self):
        """The failure this scale exists to end. Catches px and rem radii
        written as literals; 50% and 999px are exempt because a circle and a
        pill are shapes rather than points on a scale."""
        offenders = []
        for match in re.finditer(r"border-radius:\s*([^;]+);", app_css()):
            value = match.group(1).strip()
            if "var(--brand-" in value or value in ("50%", "999px", "0"):
                continue
            offenders.append(value)
        self.assertEqual(offenders, [])


class TheNightAxisIsTokenLevel(TestCase):
    def test_no_component_names_a_night_colour(self):
        """The whole mechanism. A component reaching for --brand-night-paper
        directly is dark in BOTH grounds, forever, and reads as a rendering
        bug rather than as the decision it was."""
        hits = re.findall(r"--brand-(?:night|\w+-lift)\b", app_css())
        self.assertEqual(sorted(set(hits)), [])

    def test_the_axis_redefines_ordinary_tokens(self):
        """It works by reassignment, not addition. If --brand-paper is not
        among what it redefines, cards stay light on a dark page."""
        css = BRAND_CSS.read_text()
        dark = css[css.index("@media (prefers-color-scheme: dark)"):]
        for token in ("--brand-birch", "--brand-paper", "--brand-ink",
                      "--brand-moss", "--brand-rule", "--brand-ochre",
                      "--brand-spruce"):
            self.assertIn(f"{token}:", dark)

    def test_it_is_scoped_to_the_application(self):
        """The public pages set their own type and carry photographs chosen
        for a warm ground. Giving them a dark mode is a separate decision."""
        css = BRAND_CSS.read_text()
        dark = css[css.index("@media (prefers-color-scheme: dark)"):]
        self.assertIn("body.app", dark)

    def test_the_app_shell_carries_the_class_the_axis_needs(self):
        self.assertIn('<body class="app">', APP_BASE.read_text())

    def test_both_accents_are_lifted_for_the_dark_ground(self):
        """Ochre sits at 4.9:1 on the night card and spruce is the link
        colour. Neither can be marginal."""
        css = BRAND_CSS.read_text()
        dark = css[css.index("@media (prefers-color-scheme: dark)"):]
        self.assertIn("--brand-ochre: var(--brand-ochre-lift)", dark)
        self.assertIn("--brand-spruce: var(--brand-spruce-lift)", dark)


class TheStreamColumnIsOptIn(TestCase):
    def test_the_shell_offers_the_block(self):
        self.assertIn("{% block main_class %}", APP_BASE.read_text())

    def test_the_community_takes_it(self):
        body = (ROOT / "site_app" / "templates" / "site_app"
                / "board.html").read_text()
        self.assertIn("{% block main_class %}stream{% endblock %}", body)

    def test_the_tabular_pages_do_not(self):
        """The warehouse and the ledger are genuinely tabular and would be
        unreadable at feed width. This is opt-in for that reason."""
        for name in ("warehouse.html", "ledger.html"):
            path = ROOT / "site_app" / "templates" / "site_app" / name
            if path.exists():
                self.assertNotIn("stream", path.read_text().split("{% block content %}")[0])


class MotionAndReach(TestCase):
    def test_motion_is_opt_out(self):
        self.assertIn("prefers-reduced-motion", app_css())

    def test_a_thumb_target_exists_for_coarse_pointers(self):
        """A feed is operated with a thumb, and type size is not reach."""
        css = app_css()
        self.assertIn("pointer:coarse", css)
        self.assertIn("var(--brand-tap)", css)
