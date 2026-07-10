from urllib.parse import parse_qs

import pytest
import requests
from django.test import override_settings

from suomifi_on_behalf.helsinki_profile import (
    HelsinkiProfileClient,
    HelsinkiProfileError,
)

HP_API = "https://profile-test.example.test/graphql/"
AUDIENCE = "profile-api-test"
SCOPE = "https://api.hel.fi/auth/helsinkiprofile"
TUNNISTUS = "https://tunnistus.example.test/api-tokens/"

PROFILE_RESPONSE = {
    "data": {
        "myProfile": {
            "verifiedPersonalInformation": {
                "nationalIdentificationNumber": "210281-9988"
            }
        }
    }
}

with_tunnistus = override_settings(
    SUOMIFI_ON_BEHALF_HELSINKI_PROFILE_API_URL=HP_API,
    SUOMIFI_ON_BEHALF_HELSINKI_PROFILE_AUDIENCE=AUDIENCE,
    SUOMIFI_ON_BEHALF_HELSINKI_PROFILE_SCOPE=SCOPE,
    SUOMIFI_ON_BEHALF_TUNNISTUS_API_TOKENS_ENDPOINT=TUNNISTUS,
)


def test_unconfigured_client_raises():
    with pytest.raises(HelsinkiProfileError, match="not configured"):
        HelsinkiProfileClient()


@override_settings(
    SUOMIFI_ON_BEHALF_HELSINKI_PROFILE_API_URL=HP_API,
    SUOMIFI_ON_BEHALF_HELSINKI_PROFILE_AUDIENCE="foo-bar",
    SUOMIFI_ON_BEHALF_HELSINKI_PROFILE_SCOPE=SCOPE,
    SUOMIFI_ON_BEHALF_TUNNISTUS_API_TOKENS_ENDPOINT=TUNNISTUS,
)
def test_get_api_access_token_uses_audience_setting(requests_mock):
    requests_mock.post(TUNNISTUS, json={SCOPE: "api-token"})

    client = HelsinkiProfileClient()

    assert client.get_api_access_token("oidc-token") == "api-token"

    request_body = parse_qs(requests_mock.request_history[0].text)
    assert request_body == {
        "audience": ["foo-bar"],
        "grant_type": ["urn:ietf:params:oauth:grant-type:uma-ticket"],
        "permission": ["#access"],
    }


@with_tunnistus
def test_get_api_access_token_missing_scope_raises(requests_mock):
    requests_mock.post(TUNNISTUS, json={})

    with pytest.raises(HelsinkiProfileError, match="HELSINKI_PROFILE_SCOPE"):
        HelsinkiProfileClient().get_api_access_token("oidc-token")


@with_tunnistus
def test_get_profile_via_tunnistus(requests_mock):
    requests_mock.post(TUNNISTUS, json={SCOPE: "api-token"})
    requests_mock.post(HP_API, json=PROFILE_RESPONSE)

    assert HelsinkiProfileClient().get_profile("oidc-token") == {
        "user_ssn": "210281-9988"
    }


@with_tunnistus
def test_get_profile_graphql_error_raises(requests_mock):
    requests_mock.post(TUNNISTUS, json={SCOPE: "api-token"})
    requests_mock.post(HP_API, json={"errors": [{"message": "boom"}]})

    with pytest.raises(HelsinkiProfileError, match="GraphQL error"):
        HelsinkiProfileClient().get_profile("oidc-token")


@with_tunnistus
def test_tunnistus_missing_scope_raises(requests_mock):
    requests_mock.post(TUNNISTUS, json={})

    with pytest.raises(HelsinkiProfileError, match="HELSINKI_PROFILE_SCOPE"):
        HelsinkiProfileClient().get_profile("oidc-token")


@with_tunnistus
def test_graphql_request_exception_is_wrapped(requests_mock):
    requests_mock.post(TUNNISTUS, json={SCOPE: "api-token"})
    requests_mock.post(HP_API, exc=requests.exceptions.ConnectionError)

    with pytest.raises(HelsinkiProfileError):
        HelsinkiProfileClient().get_profile("oidc-token")


@with_tunnistus
def test_tunnistus_token_request_exception_is_wrapped(requests_mock):
    requests_mock.post(TUNNISTUS, exc=requests.exceptions.ConnectionError)

    with pytest.raises(HelsinkiProfileError):
        HelsinkiProfileClient().get_profile("oidc-token")
