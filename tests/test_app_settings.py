from django.test import override_settings

from suomifi_on_behalf import app_settings


def test_defaults_when_unset():
    # These settings are not defined in tests/settings.py, so they return defaults.
    assert app_settings.OIDC_VERIFY_SSL is True
    assert app_settings.OIDC_TIMEOUT is None
    assert app_settings.OIDC_PROXY is None
    assert app_settings.HELSINKI_PROFILE_API_URL == ""
    assert app_settings.HELSINKI_PROFILE_AUDIENCE == ""
    assert app_settings.HELSINKI_PROFILE_SCOPE == ""
    assert app_settings.TUNNISTUS_API_TOKENS_ENDPOINT == ""


@override_settings(
    SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_BASE_URL="https://example.test",
    SUOMIFI_ON_BEHALF_OIDC_VERIFY_SSL=False,
)
def test_reads_namespaced_setting():
    assert app_settings.EAUTHORIZATIONS_BASE_URL == "https://example.test"
    assert app_settings.OIDC_VERIFY_SSL is False


@override_settings(SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_CLIENT_ID="abc123")
def test_lazy_access_reflects_overrides():
    # Access happens at call time, so override_settings takes effect.
    assert app_settings.EAUTHORIZATIONS_CLIENT_ID == "abc123"
