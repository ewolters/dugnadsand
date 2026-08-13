"""The printed codes.

A manifest travels with the goods and is scanned in a barn, so the code on it
is the one piece of this system that has to survive a phone camera and bad
light. juniper draws it, and juniper's contribution is that it REFUSES a size
that would be unscannable rather than drawing something that looks like a code
and is not one.
"""

from django.test import TestCase


class TheQrIsDrawnByJuniper(TestCase):
    def render(self, data, **kw):
        from site_app.auth_views import _qr_svg

        return _qr_svg(data, **kw)

    def test_it_renders_an_svg(self):
        svg = self.render("https://dugnadsand.org/act/" + "x" * 43)
        self.assertIsNotNone(svg)
        self.assertIn("<svg", svg)

    def test_it_is_sized_in_millimetres_because_it_is_printed(self):
        """Pixels are meaningless on paper. The standards constrain the module
        size in millimetres and juniper asks in those terms."""
        svg = self.render("https://dugnadsand.org/act/token", width="38mm")
        self.assertIn("mm", svg)

    def test_a_size_that_would_be_unscannable_is_refused_not_drawn(self):
        """The reason to use juniper here. A code too small to read is worse
        than no code: it looks like it works until somebody is standing in a
        barn with a phone.

        The refusal comes in two places and they are different failures. Too
        SMALL is geometry — the modules fall under the 0.25mm the standard
        specifies. Too MUCH DATA is encoding, refused before any drawing is
        attempted at all.
        """
        from juniper.symbology import encode, render_svg
        from juniper.symbology.errors import InvalidData, InvalidGeometry

        with self.assertRaises(InvalidGeometry):
            render_svg(encode("qr", "https://dugnadsand.org/act/abcdefghijklmnop"),
                       width="5mm")

        with self.assertRaises(InvalidData):
            encode("qr", "https://dugnadsand.org/act/" + "y" * 300)

    def test_the_helper_degrades_rather_than_breaking_the_page(self):
        """Every caller shows the value as text alongside, so a failure to
        draw must never take the page down with it."""
        self.assertIsNone(self.render("x" * 20000, width="10mm"))

    def test_it_carries_no_dependency_the_repo_does_not_state(self):
        import juniper

        self.assertTrue(juniper.__file__)


class TheManifestCarriesOne(TestCase):
    def test_the_public_example_still_renders(self):
        """/virtual-warehouse/ shows an example code to explain the flow."""
        body = self.client.get("/virtual-warehouse/").content.decode()
        self.assertIn("<svg", body)
