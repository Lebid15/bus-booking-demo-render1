from django.urls import path

from identity.views import (
    LoginView,
    MfaVerifyView,
    RegisterView,
    RegistrationVerifyView,
    SessionListView,
    SessionRevokeView,
)

urlpatterns = [
    path("auth/register", RegisterView.as_view(), name="auth-register"),
    path("auth/register/verify", RegistrationVerifyView.as_view(), name="auth-register-verify"),
    path("auth/login", LoginView.as_view(), name="auth-login"),
    path("auth/mfa/verify", MfaVerifyView.as_view(), name="auth-mfa-verify"),
    path("me/sessions", SessionListView.as_view(), name="me-sessions"),
    path("me/sessions/<uuid:session_id>", SessionRevokeView.as_view(), name="me-session-revoke"),
]
