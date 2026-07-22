from django.urls import path

from policies.views import (
    OfficeConfigurationView,
    PlatformConfigurationView,
    PlatformPolicyListCreateView,
    PublicPolicyDetailView,
)

urlpatterns = [
    path("platform/policies", PlatformPolicyListCreateView.as_view(), name="platform-policies"),
    path("platform/configuration", PlatformConfigurationView.as_view(), name="platform-configuration"),
    path("office/configuration", OfficeConfigurationView.as_view(), name="office-configuration"),
    path("public/policies/<str:policy_code>", PublicPolicyDetailView.as_view(), name="public-policy-detail"),
]
