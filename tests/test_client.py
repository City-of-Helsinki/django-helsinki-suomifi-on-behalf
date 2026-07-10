import re

import pytest
import requests

from suomifi_on_behalf import app_settings
from suomifi_on_behalf.client import (
    SignedUserinfoNotSupportedError,
    get_userinfo,
    request_organization_roles,
)
from suomifi_on_behalf.signals import suomifi_mandate_query_failed


@pytest.mark.django_db
def test_get_userinfo_returns_json_claims(session_request, requests_mock):
    session_request.session["oidc_access_token"] = "t"
    requests_mock.get(
        "http://example.test/userinfo",
        json={"national_id_num": "210281-9988"},
    )

    assert get_userinfo(session_request) == {"national_id_num": "210281-9988"}


@pytest.mark.django_db
def test_get_userinfo_rejects_signed_jwt(session_request, requests_mock):
    session_request.session["oidc_access_token"] = "t"
    requests_mock.get(
        "http://example.test/userinfo",
        text="eyJ.signed.jwt",
        headers={"content-type": "application/jwt"},
    )

    with pytest.raises(SignedUserinfoNotSupportedError):
        get_userinfo(session_request)


@pytest.mark.django_db
def test_request_organization_roles_returns_roles(session_request, requests_mock):
    roles = {
        "name": "Activenakusteri Oy",
        "identifier": "7769480-5",
        "roles": ["NIMKO"],
    }
    matcher = re.compile(re.escape(app_settings.EAUTHORIZATIONS_BASE_URL))
    requests_mock.get(matcher, json=[roles])

    result = request_organization_roles(session_request)

    assert result == roles
    assert session_request.session["organization_roles"] == roles


@pytest.mark.django_db
def test_request_organization_roles_failure_sends_signal(
    session_request, requests_mock
):
    matcher = re.compile(re.escape(app_settings.EAUTHORIZATIONS_BASE_URL))
    requests_mock.get(matcher, exc=requests.exceptions.ConnectionError)

    received = []

    def handler(sender, **kwargs):
        received.append(kwargs)

    suomifi_mandate_query_failed.connect(handler)
    try:
        with pytest.raises(requests.exceptions.ConnectionError):
            request_organization_roles(session_request)
    finally:
        suomifi_mandate_query_failed.disconnect(handler)

    assert received and "error" in received[0]
