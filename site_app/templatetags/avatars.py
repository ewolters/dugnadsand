"""{% avatar member %} — a person's mark, wherever a person is named."""

from django import template

from site_app import avatars

register = template.Library()


@register.simple_tag(name="avatar")
def avatar(member, size=28):
    if member is None:
        return ""
    return avatars.svg(member, size=size)


@register.simple_tag(name="avatar_in")
def avatar_in(member, colour, size=28):
    """The same person's mark, forced to one colour, saving nothing.

    For the picker: a swatch shows the paint, this shows the thing you will
    actually be.
    """
    if member is None:
        return ""
    return avatars.svg(member, size=size, colour=colour)
