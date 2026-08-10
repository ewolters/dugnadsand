"""{% avatar member %} — a person's mark, wherever a person is named."""

from django import template

from site_app import avatars

register = template.Library()


@register.simple_tag(name="avatar")
def avatar(member, size=28):
    if member is None:
        return ""
    return avatars.svg(member, size=size)
