"""@ somebody, $ something — resolved when the page is drawn, never stored.

PARSE, DO NOT STORE. There is no Mention model and there must not be. A row
joining a comment to a member is countable, and "Ada was mentioned forty times"
is a popularity score — which is the thing no-aggregate-display exists to
prevent, arriving through a door nobody was watching. The comment body is the
only record; everything below is derived at render time.

It also degrades correctly, which a stored link would not. Stock gets used up,
members leave, descriptions get edited. A stored reference rots into a dangling
id; a derived one quietly becomes plain text again, which is what somebody
reading an old comment should see.

AMBIGUITY IS LEFT ALONE. Two members called Ada, or three stock lines
mentioning oak, and the mention stays plain text. Guessing which one was meant
would be wrong some of the time and silent about it every time — and for a
mention, wrong means notifying somebody who was not being spoken to.

ORDER MATTERS FOR SAFETY. The body is user input. It is escaped FIRST and the
anchors are inserted into the escaped string, so no comment can inject markup.
The sigils and word characters this matches survive escaping unchanged, which
is what makes that order possible.
"""

import re

from django.utils.html import escape
from django.utils.safestring import mark_safe

# One-line change if these ever move. `$` reads as currency in a system whose
# premise is that nothing here has a price — worth knowing when picking it.
PERSON = "@"
RESOURCE = "$"

# A sigil, then a run of word characters or hyphens. Deliberately narrow:
# anything longer invites matching across whitespace, which turns a sentence
# into a mention.
_PERSON_RE = re.compile(re.escape(PERSON) + r"([\w][\w-]{0,39})")
_RESOURCE_RE = re.compile(re.escape(RESOURCE) + r"([\w][\w-]{0,39})")


def _one_member(token):
    """The single member this names, or None. RLS scopes it to the tenant."""
    from .models import Member

    matches = list(Member.objects.filter(display_name__istartswith=token)[:2])
    return matches[0] if len(matches) == 1 else None


def _one_line(token):
    """The single available stock line this names, or None."""
    from .models import StockLine

    matches = list(
        StockLine.objects.filter(available=True)
        .filter(description__icontains=token)
        .select_related("warehouse")[:2])
    return matches[0] if len(matches) == 1 else None


def mentioned_members(body, exclude_member=None):
    """Members named in this text. For notifying them, and nothing else.

    Returns each member once however many times they were written. Somebody
    who says "@ada" three times in one comment has not asked three times.
    """
    found = {}
    for token in _PERSON_RE.findall(body or ""):
        member = _one_member(token)
        if member is None:
            continue
        if exclude_member is not None and member.id == exclude_member.id:
            continue
        found[member.id] = member
    return list(found.values())


def render(body):
    """The comment as safe HTML, with what resolves turned into links.

    What does not resolve stays as written. A reader seeing plain "$oak" in an
    old comment is being told the truth: whatever that was, it is not on the
    shelf now.
    """
    text = escape(body or "")

    def person(match):
        member = _one_member(match.group(1))
        if member is None:
            return match.group(0)
        return (f'<span class="mention person" title="{escape(member.display_name)}">'
                f'{escape(PERSON)}{escape(match.group(1))}</span>')

    def resource(match):
        line = _one_line(match.group(1))
        if line is None:
            return match.group(0)
        return (f'<a class="mention resource" '
                f'href="/warehouse/{line.warehouse_id}/">'
                f'{escape(RESOURCE)}{escape(match.group(1))}</a>')

    text = _PERSON_RE.sub(person, text)
    text = _RESOURCE_RE.sub(resource, text)
    # Written after escaping, so the only markup present is what this built.
    return mark_safe(text.replace("\n", "<br>"))


def announce_mentions(comment):
    """Tell whoever was named. Told, never asked.

    Same rule as everywhere else: the notice carries no words of the comment
    and no name, because it travels through the shared platform table. And the
    author learns nothing about who read it — being mentioned is not being
    asked, and a mention that reported back would make it one.
    """
    from .notifications import _send

    sent = 0
    for member in mentioned_members(comment.body, exclude_member=comment.member):
        user = member.user
        email = user.email if user else ""
        if email and _send(email, "mentioned",
                           "Somebody mentioned you in a comment.",
                           "/board/"):
            sent += 1
    return sent
