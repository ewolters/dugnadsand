from django.urls import path

from . import auth_views, views

app_name = "site_app"

urlpatterns = [
    path("", views.index, name="index"),
    path("login/", views.member_login, name="login"),
    path("logout/", views.member_logout, name="logout"),
    path("board/", views.board, name="board"),
    path("board/new/", views.posting_new, name="posting_new"),
    path("board/<uuid:posting_id>/claim/", views.claim_posting, name="claim_posting"),
    path("board/<uuid:posting_id>/step-off/", views.step_off, name="step_off"),
    path("board/<uuid:posting_id>/close/", views.posting_close, name="posting_close"),
    path("board/<uuid:posting_id>/hours/", views.contribution_new, name="contribution_new"),
    path("ledger/", views.ledger, name="ledger"),
    path("projects/", views.projects, name="projects"),
    path("projects/new/", views.project_new, name="project_new"),
    path("projects/<uuid:project_id>/", views.project_detail, name="project_detail"),
    path("projects/<uuid:project_id>/close/", views.project_close, name="project_close"),
    path("notices/", views.notices, name="notices"),
    path("password/", views.change_password, name="change_password"),
    path("mfa/", auth_views.mfa_challenge, name="mfa_challenge"),
    path("mfa/setup/", auth_views.mfa_setup, name="mfa_setup"),
    path("sso/", auth_views.sso_entry, name="sso_entry"),
    path("setup/<str:token>/", auth_views.setup, name="setup"),
    path("members/", views.members, name="members"),
    path("members/new/", views.member_new, name="member_new"),
    path("attestation/", views.attestation, name="attestation"),
    path("attestation/run/", views.attestation_run, name="attestation_run"),
]
