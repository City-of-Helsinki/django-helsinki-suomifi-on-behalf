from django.urls import path

from suomifi_on_behalf.views import (
    EauthAuthenticationCallbackView,
    EauthAuthenticationRequestView,
)

urlpatterns = [
    path(
        "eauthorizations/authenticate/",
        EauthAuthenticationRequestView.as_view(),
        name="eauth_authentication_init",
    ),
    path(
        "eauthorizations/callback/",
        EauthAuthenticationCallbackView.as_view(),
        name="eauth_authentication_callback",
    ),
]
