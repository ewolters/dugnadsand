"""Render a comment body with its @ and $ resolved.

A filter rather than work done in the view because a comment is rendered in
several places and the resolution must not drift between them.
"""

from django import template

from site_app import mentions

register = template.Library()


@register.filter(name="mentions")
def render_mentions(body):
    return mentions.render(body)
