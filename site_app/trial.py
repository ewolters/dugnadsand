"""The trial interest period, in one place.

Dugnadsand is running as a trial while whether it continues is decided. Two
public doors are affected and they are affected for different reasons, so both
are stated here rather than inferred from a flag somewhere.

APPLICATIONS ARE CLOSED because admitting an organization is a commitment to
operate the network for it, and that commitment cannot honestly be made while
the network's future is undecided. An organization admitted in September into
something that closes in October has been done a disservice, not a favour.

BLIND REQUESTS ARE CLOSED because of arithmetic rather than policy. A request
is shown to the mutual aid groups covering its area and to nobody else, so with
no group reading them a request reaches nobody at all — and the form would
collect a name and a phone number from somebody having the worst week of their
year and put them in a queue with no reader. A page that cannot help should say
so rather than take the details.

Reopening either is deleting a constant, and the pages read the constants
rather than hardcoding a date, so the two cannot drift.
"""

from datetime import date

# When the trial period runs to. Whether the network continues past this is
# the thing being decided; the date is not a promise that it will.
TRIAL_ENDS = date(2026, 9, 30)

APPLICATIONS_OPEN = False
REQUESTS_OPEN = False

# Where somebody who needs help now should actually go. Named specifically
# rather than "search online", because a person in trouble is being turned
# away from this page and deserves a real destination rather than a gesture.
ELSEWHERE = [
    ("211", "Dial 2-1-1, or 211.org — free, confidential, 24 hours, and the "
            "standard route to food, housing, utilities and crisis help "
            "across South Carolina and North Carolina."),
    ("988", "Dial 9-8-8 for the Suicide and Crisis Lifeline, any time."),
    ("Emergencies", "Dial 9-1-1."),
]


def ends_on():
    """The date, formatted the way the public pages write dates."""
    return TRIAL_ENDS.strftime("%-d %B %Y")
