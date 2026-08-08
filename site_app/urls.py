from django.urls import path

from . import views

app_name = "site_app"

urlpatterns = [
    path("", views.index, name="index"),
    path("offerings/<uuid:offering_id>/claim/", views.claim_offering, name="claim_offering"),
    path("attestation/", views.attestation, name="attestation"),
    path("attestation/run/", views.attestation_run, name="attestation_run"),
]
