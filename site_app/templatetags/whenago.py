"""How long ago, said the way a person says it.

"12 AUG" is a filing date. On a feed the useful fact is almost always how
long ago, and Django's timesince gives "2 hours, 34 minutes" — two units and
a comma, which is a duration rather than a timestamp.

Nothing here counts anything about a person. It is a fact about one row.
"""

from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def ago(when):
    if not when:
        return ""

    seconds = (timezone.now() - when).total_seconds()
    if seconds < 0:
        return "just now"

    minutes = seconds / 60
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{int(minutes)}m ago"

    hours = minutes / 60
    if hours < 24:
        return f"{int(hours)}h ago"

    days = hours / 24
    if days < 7:
        return f"{int(days)}d ago"
    if days < 365:
        # Past a week the day of the month is more use than a count of weeks:
        # "3w ago" and "24 Aug" answer different questions, and by then the
        # question is which day.
        return when.strftime("%-d %b")
    return when.strftime("%-d %b %Y")
