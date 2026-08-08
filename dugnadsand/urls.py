from django.urls import include, path

from kjerne_platform.varta.urls import get_urlpatterns as varta_urls

# Django admin is deliberately NOT mounted. It came from the create-site
# scaffold with no models registered, so it was pure attack surface, and every
# other site in the fleet leaves it off. Members sign in through the in-app
# login; organizations and memberships are created by management command,
# because admission is a decision somebody makes rather than a form somebody
# fills in. site_app/tests/test_onboarding.py asserts it stays unmounted.
urlpatterns = [
    path("", include("site_app.urls")),
] + varta_urls()
