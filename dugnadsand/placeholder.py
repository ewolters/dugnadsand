"""The placeholder, off by default.

Set DUGNADSAND_PLACEHOLDER=1 to put it up. While it is up, every public request
gets templates/placeholder.html; nothing is deleted, disabled or migrated, and
taking it down restores the site exactly rather than approximately. After
changing it:

    ~/ctrl/collect-static ~/dugnadsand && systemctl --user restart dugnadsand

The same shape as ouat's and svend's, so one reader learns all three.

/admin/, /static/, /media/ and /health/ stay reachable on purpose. The front
door being shut should not take the operator's own tools away, and a health
check answering 200 keeps a closed site from reading as an outage to the fleet.
"""

import os
import sys

from django.shortcuts import render

# Inert under the test runner. The suite tests the SITE, which still exists in
# full; the placeholder is a deployment state rather than a behaviour, and
# letting it answer would turn 962 real tests into assertions about one static
# page.
_UNDER_TEST = "test" in sys.argv

PLACEHOLDER = os.environ.get("DUGNADSAND_PLACEHOLDER", "0") != "0" and not _UNDER_TEST

# Paths that answer normally while the placeholder is up.
PASS_THROUGH = ("/admin/", "/static/", "/media/", "/health/")


class PlaceholderMiddleware:
    """Serve the placeholder instead of the site.

    Deliberately a middleware rather than a change to urls.py: the routes,
    views and templates stay untouched and unreferenced by this, so turning it
    off restores the site as it was rather than as someone remembered it.

    It sits high in the chain but AFTER SecurityMiddleware, so HSTS and the SSL
    redirect still apply to a site that is closed rather than gone.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not PLACEHOLDER or request.path.startswith(PASS_THROUGH):
            return self.get_response(request)
        # 503 rather than 200: a closed site is not a page about closing, and a
        # crawler that reads 200 will index the notice in place of every URL it
        # already holds. Retry-After is omitted deliberately — it states a
        # return, and this notice does not promise one.
        response = render(request, "placeholder.html", status=503)
        response["Cache-Control"] = "no-store"
        return response
