import pytest
from django.test import RequestFactory, override_settings

from suomifi_on_behalf.sessions import (
    get_eauth_login_success_url,
    is_safe_redirect_url,
    store_token_info_in_session,
)


def _request(secure=False):
    return RequestFactory().get("/", secure=secure)


def test_is_safe_redirect_url_rejects_empty():
    assert is_safe_redirect_url(_request(), "") is False


def test_is_safe_redirect_url_rejects_foreign_host():
    assert (
        is_safe_redirect_url(
            _request(),
            "https://evil.example.test/x",
            allowed_hosts=["good.example.test"],
        )
        is False
    )


@override_settings(SUOMIFI_ON_BEHALF_REDIRECT_REQUIRE_HTTPS=None)
def test_is_safe_redirect_url_require_https_falls_back_to_request():
    # SUOMIFI_ON_BEHALF_REDIRECT_REQUIRE_HTTPS is unset, so it falls back to
    # request.is_secure() (True here), which permits the same-host https URL.
    request = _request(secure=True)
    assert is_safe_redirect_url(request, "https://testserver/next") is True


@pytest.mark.django_db
@override_settings(LOGIN_REDIRECT_URL="http://example.test/ok")
def test_login_success_url_falls_back_to_login_redirect_url(session_request):
    # No eauth_next_url in the session -> falls back to LOGIN_REDIRECT_URL.
    assert get_eauth_login_success_url(session_request) == "http://example.test/ok"


@pytest.mark.django_db
def test_store_token_info_includes_refresh_expiry(session_request):
    result = store_token_info_in_session(
        session_request, {"refresh_expires_in": 600}, "eauth"
    )
    assert "eauth_refresh_token_expires" in result
