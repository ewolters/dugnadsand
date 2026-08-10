"""Context the app chrome needs on every page, rather than on the pages that
happened to remember.

`member` is read by the header — the account menu shows a person's mark and
their name — so every rendered app page needs it. Passing it per view meant
the menu said "Ada" on the pages that included it and fell back to "You" on
the ones that did not, which nobody noticed because the fallback was graceful.
Chrome data belongs to the chrome.
"""


def member(request):
    """The signed-in member, or nothing.

    Reads through the reverse one-to-one, which raises rather than returning
    None when there is no membership — an authenticated user with no member
    row is a real state here (an SSO visitor who belongs to no organization).
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    try:
        return {"member": user.member}
    except Exception:
        # No membership, or the row is out of reach of this request's tenant.
        # Either way the chrome renders its own fallback.
        return {}
