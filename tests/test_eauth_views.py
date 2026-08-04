import re
from datetime import datetime
from unittest import mock

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time

from suomifi_on_behalf import app_settings
from suomifi_on_behalf.client import get_checksum_header, get_organization_roles
from suomifi_on_behalf.ssn import SsnResolutionError


@freeze_time("2017-02-09T10:29:42.09")
@override_settings(
    SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_CLIENT_ID="ed4b7ae7",
    SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_CLIENT_SECRET="3ba56df8-88b8-4805-9b04-2f8e7a61",
)
def test_get_checksum_header():
    """
    Docs (only in Finnish):
    Search for "Tarkistesumman laskemiseen toteutetun funktion verifiointi":
    https://palveluhallinta.suomi.fi/fi/tuki/artikkelit/5a781dc75cb4f10dde9735e4

    Checksum verification:
    path = (
        "/service/hpa/user/register/ed4b7ae7/080297-915A"
        "?requestId=02fd35dc-99e6-477b-b6e2-03f02cbf3666"
    )
    client_id = "ed4b7ae7"
    client_secret = "3ba56df8-88b8-4805-9b04-2f8e7a61"
    time_stamp = "2017-02-09T10:29:42.090000+00:00"
    __________________
    Result:
    ed4b7ae7 2017-02-09T10:29:42.090000+00:00
        GeRKoGmGd0RFk33s2vNHutJf/TrEdwSM2Vb7qWXLESY=
    """
    path = "/service/hpa/user/register/ed4b7ae7/080297-915A?requestId=02fd35dc-99e6-477b-b6e2-03f02cbf3666"  # noqa: E501
    checksum = get_checksum_header(path)

    assert (
        checksum == "ed4b7ae7 2017-02-09T10:29:42.090000+00:00"
        " GeRKoGmGd0RFk33s2vNHutJf/TrEdwSM2Vb7qWXLESY="
    )


@pytest.mark.django_db
@override_settings(
    SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_BASE_URL="http://example.test",
    SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_CLIENT_ID="test",
    SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_CLIENT_SECRET="test",
)
def test_get_organization_roles(session_request, requests_mock):
    organization_roles_json = [
        {
            "name": "Activenakusteri Oy",
            "identifier": "7769480-5",
            "complete": True,
            "roles": ["NIMKO"],
        }
    ]

    matcher = re.compile(re.escape(app_settings.EAUTHORIZATIONS_BASE_URL))
    requests_mock.get(matcher, json=organization_roles_json)

    organization_roles = get_organization_roles(session_request)

    assert organization_roles["name"] == organization_roles_json[0]["name"]
    assert organization_roles["identifier"] == organization_roles_json[0]["identifier"]
    assert session_request.session["organization_roles"] == organization_roles_json[0]


@pytest.mark.django_db
@override_settings(
    SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_BASE_URL="http://example.test",
    SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_CLIENT_ID="test",
    SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_CLIENT_SECRET="test",
)
def test_eauth_authentication_init_view(requests_mock, user_client, user):
    register_user_info = {
        "sessionId": "test_session",
        "userId": "test_user",
    }

    matcher = re.compile(re.escape(app_settings.EAUTHORIZATIONS_BASE_URL))
    requests_mock.get(matcher, json=register_user_info)

    authentication_url = reverse("eauth_authentication_init")

    userinfo = {
        "national_id_num": "210281-9988",
    }

    with mock.patch("suomifi_on_behalf.ssn.get_userinfo", return_value=userinfo):
        response = user_client.get(authentication_url)

    assert response.status_code == 302
    assert app_settings.EAUTHORIZATIONS_BASE_URL in response.url
    assert "test_user" in response.url


@pytest.mark.django_db
@override_settings(
    SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_CLIENT_ID="ed4b7ae7",
    SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_BASE_URL="http://example.test",
    SUOMIFI_ON_BEHALF_LOGIN_SUCCESS_URL="http://example.test/success",
    SUOMIFI_ON_BEHALF_REDIRECT_ALLOWED_HOSTS=["example.test"],
    SUOMIFI_ON_BEHALF_REDIRECT_REQUIRE_HTTPS=False,
)
def test_eauth_callback_view(requests_mock, user_client, user):
    token_info = {
        "access_token": "test2",
        "expires_in": 600,
        "refresh_token": "test3",
    }
    matcher = re.compile(re.escape(app_settings.EAUTHORIZATIONS_BASE_URL))
    requests_mock.post(matcher, json=token_info)

    organization_roles_json = [
        {
            "name": "Activenakusteri Oy",
            "identifier": "7769480-5",
            "complete": True,
            "roles": ["NIMKO"],
        }
    ]
    requests_mock.get(matcher, json=organization_roles_json)

    callback_url = f"{reverse('eauth_authentication_callback')}?code=test"

    # First test: With explicit next URL in session
    session = user_client.session
    session["eauth_next_url"] = "http://example.test/dynamic/redirect/"
    session.save()

    response = user_client.get(callback_url)

    assert response.status_code == 302
    assert response.url == "http://example.test/dynamic/redirect/"

    # Verify the value was popped from the session
    assert "eauth_next_url" not in user_client.session

    access_token_expires = timezone.now() + timezone.timedelta(seconds=600)
    assert user_client.session.get("eauth_access_token") == "test2"
    assert user_client.session.get("eauth_refresh_token") == "test3"
    assert abs(
        datetime.fromisoformat(user_client.session.get("eauth_access_token_expires"))
        - access_token_expires
    ) < timezone.timedelta(seconds=10)
    assert user_client.session["organization_roles"] == organization_roles_json[0]


@pytest.mark.django_db
def test_init_view_resolver_failure_redirects_to_error_url(user_client, user):
    def failing_resolver(request):
        raise SsnResolutionError("no ssn")

    with mock.patch(
        "suomifi_on_behalf.views.get_ssn_resolver", return_value=failing_resolver
    ):
        response = user_client.get(reverse("eauth_authentication_init"))

    assert response.status_code == 302
    assert response.url == app_settings.LOGIN_ERROR_URL


@pytest.mark.django_db
@override_settings(SUOMIFI_ON_BEHALF_LOGIN_SUCCESS_URL="")
def test_init_view_requires_login_success_url(user_client, user):
    # The init view fails fast rather than letting the misconfiguration surface at the
    # end of the callback.
    with pytest.raises(ImproperlyConfigured):
        user_client.get(reverse("eauth_authentication_init"))


@pytest.mark.django_db
def test_init_view_includes_language(requests_mock, user_client, user):
    requests_mock.get(
        re.compile(re.escape(app_settings.EAUTHORIZATIONS_BASE_URL)),
        json={"sessionId": "s", "userId": "u"},
    )
    user_client.cookies["django_language"] = "fi"

    with mock.patch(
        "suomifi_on_behalf.ssn.get_userinfo",
        return_value={"national_id_num": "210281-9988"},
    ):
        response = user_client.get(reverse("eauth_authentication_init"))

    assert response.status_code == 302
    assert "lang=fi" in response.url


@pytest.mark.django_db
def test_callback_error_logs_out_and_fails(user_client, user):
    user_client.cookies["django_language"] = "fi"
    response = user_client.get(
        f"{reverse('eauth_authentication_callback')}?error=access_denied"
    )

    assert response.status_code == 302
    assert "/fi/" in response.url


@pytest.mark.django_db
def test_callback_token_error_redirects_to_failure(requests_mock, user_client, user):
    requests_mock.post(
        re.compile(re.escape(app_settings.EAUTHORIZATIONS_BASE_URL)),
        status_code=400,
    )

    response = user_client.get(f"{reverse('eauth_authentication_callback')}?code=test")

    assert response.status_code == 302


@pytest.mark.django_db
def test_callback_without_code_or_error_fails(user_client, user):
    response = user_client.get(reverse("eauth_authentication_callback"))

    assert response.status_code == 302


@pytest.mark.django_db
def test_callback_success_appends_language(requests_mock, user_client, user):
    matcher = re.compile(re.escape(app_settings.EAUTHORIZATIONS_BASE_URL))
    requests_mock.post(matcher, json={"access_token": "a", "expires_in": 600})
    requests_mock.get(
        matcher, json=[{"name": "Org", "identifier": "1", "roles": ["NIMKO"]}]
    )

    session = user_client.session
    session["eauth_next_url"] = "http://example.test/dyn/"
    session.save()
    user_client.cookies["django_language"] = "fi"

    response = user_client.get(f"{reverse('eauth_authentication_callback')}?code=test")

    assert response.status_code == 302
    assert response.url == "http://example.test/dyn/fi/"
