from django.contrib import admin
from django.urls import include, path

from kjerne_platform.varta.urls import get_urlpatterns as varta_urls

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("site_app.urls")),
] + varta_urls()
