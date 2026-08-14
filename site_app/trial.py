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

# --------------------------------------------------------------------------
# Named local services.
#
# CHECKED_ON is on the page for a reason. Nothing here can keep itself
# current: organizations move, numbers change, and a directory that looks
# authoritative while being three years stale sends somebody in trouble to a
# dead line — which is worse than sending them nowhere, because they stop
# looking. The date lets a reader judge it, and 2-1-1 above is the maintained
# directory this one cannot be.
#
# That is not hypothetical here. MANNA FoodBank's warehouse is at Mills River
# now, and search results, review sites and older guides still list Swannanoa
# River Road, which flooded. Every entry below was read off the organization's
# own page or its own listing on CHECKED_ON.
# --------------------------------------------------------------------------

CHECKED_ON = date(2026, 8, 14)

LOCAL = [
    ("Greenville, South Carolina", [
        ("United Ministries",
         "(864) 232-6463 · 606 Pendleton Street",
         "Food, help with rent, utilities and medication, and a day shelter "
         "with showers, laundry, lockers, a telephone and help replacing "
         "identification."),
        ("Greenville Free Medical Clinic",
         "(864) 232-1470 · 600 Arlington Avenue",
         "Medical and dental care and prescriptions, without charge, for "
         "uninsured Greenville County residents."),
        ("Miracle Hill — Greenville Rescue Mission",
         "(864) 242-6933 · 575 West Washington Street",
         "Emergency shelter for men, with meals and clothing. A Christian "
         "ministry."),
        ("Safe Harbor",
         "(800) 291-2139, 24 hours · locally (864) 467-3636",
         "Domestic violence: shelter, counselling and help with the courts. "
         "Free and confidential."),
    ]),
    ("Asheville and Buncombe County, North Carolina", [
        ("ABCCM Crisis Ministry",
         "(828) 259-5300 · 24 Cumberland Avenue",
         "Emergency food, financial assistance and case management. Also at "
         "Arden (828) 259-5302, Candler (828) 259-5301 and Weaverville "
         "Highway (828) 259-5303."),
        ("MANNA FoodBank — Food Helpline",
         "(828) 290-9749, call or text",
         "Finds the nearest pantry or meal site across sixteen counties, and "
         "helps with SNAP applications. The warehouse is at 99 Broadpointe "
         "Drive, Mills River — older listings still give the Swannanoa River "
         "Road address."),
        ("ABCCM Medical Ministry",
         "(828) 259-5339 · 155 Livingston Street",
         "A free clinic for people without insurance: medical care, dental "
         "care and medicine. Its pharmacy is at 356 Biltmore Avenue, "
         "suite 205."),
        ("Homeward Bound of WNC — AHOPE Day Center",
         "(828) 579-3479 · 19 North Ann Street",
         "Day centre, street outreach and housing for people who are "
         "homeless."),
        ("Helpmate",
         "(828) 254-0516, 24 hours",
         "Domestic violence: free emergency shelter, counselling and safety "
         "planning."),
    ]),
]


def ends_on():
    """The date, formatted the way the public pages write dates."""
    return TRIAL_ENDS.strftime("%-d %B %Y")


def checked_on():
    return CHECKED_ON.strftime("%-d %B %Y")
