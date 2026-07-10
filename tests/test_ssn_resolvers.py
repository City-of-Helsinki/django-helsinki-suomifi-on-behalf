from unittest import mock

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from suomifi_on_behalf.client import SignedUserinfoNotSupportedError
from suomifi_on_behalf.helsinki_profile import HelsinkiProfileError
from suomifi_on_behalf.ssn import (
    ChainSsnResolver,
    HelsinkiProfileSsnResolver,
    OidcUserinfoSsnResolver,
    SsnResolutionError,
    get_ssn_resolver,
)


class FakeRequest:
    def __init__(self, session=None):
        self.session = session if session is not None else {}


class TestOidcUserinfoSsnResolver:
    def test_returns_claim(self):
        request = FakeRequest(session={"oidc_access_token": "t"})
        with mock.patch(
            "suomifi_on_behalf.ssn.get_userinfo",
            return_value={"national_id_num": "210281-9988"},
        ):
            assert OidcUserinfoSsnResolver()(request) == "210281-9988"

    def test_raises_without_access_token(self):
        request = FakeRequest(session={})
        with pytest.raises(SsnResolutionError, match="oidc_access_token"):
            OidcUserinfoSsnResolver()(request)

    def test_raises_when_claim_absent(self):
        request = FakeRequest(session={"oidc_access_token": "t"})
        with mock.patch("suomifi_on_behalf.ssn.get_userinfo", return_value={}):
            with pytest.raises(SsnResolutionError, match="national_id_num"):
                OidcUserinfoSsnResolver()(request)

    def test_custom_claim_via_subclass(self):
        class CustomClaimResolver(OidcUserinfoSsnResolver):
            claim = "hetu"

        request = FakeRequest(session={"oidc_access_token": "t"})
        with mock.patch(
            "suomifi_on_behalf.ssn.get_userinfo",
            return_value={"hetu": "210281-9988"},
        ):
            assert CustomClaimResolver()(request) == "210281-9988"

    def test_wraps_signed_userinfo_error(self):
        request = FakeRequest(session={"oidc_access_token": "t"})
        with mock.patch(
            "suomifi_on_behalf.ssn.get_userinfo",
            side_effect=SignedUserinfoNotSupportedError("signed"),
        ):
            with pytest.raises(SsnResolutionError, match="signed"):
                OidcUserinfoSsnResolver()(request)


class TestHelsinkiProfileSsnResolver:
    def test_returns_ssn(self):
        request = FakeRequest(session={"oidc_access_token": "t"})
        client = mock.MagicMock()
        client.get_profile.return_value = {"user_ssn": "210281-9988"}
        with mock.patch(
            "suomifi_on_behalf.ssn.HelsinkiProfileClient", return_value=client
        ):
            assert HelsinkiProfileSsnResolver()(request) == "210281-9988"

    def test_raises_without_access_token(self):
        request = FakeRequest(session={})
        with pytest.raises(SsnResolutionError, match="oidc_access_token"):
            HelsinkiProfileSsnResolver()(request)

    def test_wraps_profile_error(self):
        request = FakeRequest(session={"oidc_access_token": "t"})
        client = mock.MagicMock()
        client.get_profile.side_effect = HelsinkiProfileError("boom")
        with mock.patch(
            "suomifi_on_behalf.ssn.HelsinkiProfileClient", return_value=client
        ):
            with pytest.raises(SsnResolutionError, match="boom"):
                HelsinkiProfileSsnResolver()(request)

    def test_raises_when_ssn_empty(self):
        request = FakeRequest(session={"oidc_access_token": "t"})
        client = mock.MagicMock()
        client.get_profile.return_value = {"user_ssn": None}
        with mock.patch(
            "suomifi_on_behalf.ssn.HelsinkiProfileClient", return_value=client
        ):
            with pytest.raises(SsnResolutionError, match="no SSN"):
                HelsinkiProfileSsnResolver()(request)


class TestChainSsnResolver:
    def test_returns_first_success(self):
        first = mock.Mock(side_effect=SsnResolutionError("nope"))
        second = mock.Mock(return_value="210281-9988")
        third = mock.Mock(return_value="unused")
        chain = ChainSsnResolver([first, second, third])

        request = FakeRequest()
        assert chain(request) == "210281-9988"
        third.assert_not_called()

    def test_raises_when_all_fail(self):
        first = mock.Mock(side_effect=SsnResolutionError("a"))
        second = mock.Mock(side_effect=SsnResolutionError("b"))
        chain = ChainSsnResolver([first, second])

        with pytest.raises(SsnResolutionError, match="All SSN resolvers failed"):
            chain(FakeRequest())


class TestGetSsnResolver:
    @override_settings(
        SUOMIFI_ON_BEHALF_SSN_RESOLVERS=[
            "suomifi_on_behalf.ssn.OidcUserinfoSsnResolver"
        ]
    )
    def test_single_entry_returns_resolver_directly(self):
        resolver = get_ssn_resolver()
        assert isinstance(resolver, OidcUserinfoSsnResolver)

    @override_settings(
        SUOMIFI_ON_BEHALF_SSN_RESOLVERS=[
            "suomifi_on_behalf.ssn.OidcUserinfoSsnResolver",
            "suomifi_on_behalf.ssn.HelsinkiProfileSsnResolver",
        ]
    )
    def test_multiple_entries_are_chained(self):
        resolver = get_ssn_resolver()
        assert isinstance(resolver, ChainSsnResolver)
        assert [type(r) for r in resolver.resolvers] == [
            OidcUserinfoSsnResolver,
            HelsinkiProfileSsnResolver,
        ]

    def test_accepts_plain_callable_entry(self):
        def my_resolver(request):
            return "210281-9988"

        with override_settings(SUOMIFI_ON_BEHALF_SSN_RESOLVERS=[my_resolver]):
            resolver = get_ssn_resolver()
            assert resolver(FakeRequest()) == "210281-9988"

    @override_settings(SUOMIFI_ON_BEHALF_SSN_RESOLVERS=None)
    def test_raises_when_unconfigured(self):
        with pytest.raises(
            ImproperlyConfigured, match="SUOMIFI_ON_BEHALF_SSN_RESOLVERS"
        ):
            get_ssn_resolver()

    @override_settings(SUOMIFI_ON_BEHALF_SSN_RESOLVERS=[object()])
    def test_raises_when_entry_not_callable(self):
        with pytest.raises(ImproperlyConfigured, match="not callable"):
            get_ssn_resolver()
