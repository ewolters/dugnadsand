from django.urls import path

from . import views

app_name = "site_app"

urlpatterns = [
    path("", views.index, name="index"),
    path("login/", views.member_login, name="login"),
    path("logout/", views.member_logout, name="logout"),
    path("offerings/", views.offerings, name="offerings"),
    path("offerings/new/", views.offering_new, name="offering_new"),
    path("offerings/<uuid:offering_id>/claim/", views.claim_offering, name="claim_offering"),
    path("offerings/<uuid:offering_id>/close/", views.offering_close, name="offering_close"),
    path("offerings/<uuid:offering_id>/hours/", views.contribution_new, name="contribution_new"),
    path("ledger/", views.ledger, name="ledger"),
    path("attestation/", views.attestation, name="attestation"),
    path("attestation/run/", views.attestation_run, name="attestation_run"),
]
