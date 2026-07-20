import re
from unittest import mock

import pytest
import requests
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from suomifi_on_behalf import app_settings
from suomifi_on_behalf.company import (
    ChainCompanyResolver,
    CompanyResolutionError,
    OrganizationRolesCompanyResolver,
    YtjCompanyResolver,
    get_company,
    get_company_resolver,
)
from suomifi_on_behalf.signals import (
    suomifi_company_resolution_failed,
    suomifi_company_resolved,
)

DUMMY_YTJ_COMPANY = {
    "businessId": {"value": "0877830-0"},
    "names": [
        {"name": "I. Haanpää Oy", "type": "1"},
        {"name": "Old name", "type": "2"},
    ],
    "companyForms": [
        {
            "type": "OY",
            "descriptions": [
                {"languageCode": "3", "description": "Limited company"},
                {"languageCode": "1", "description": "Osakeyhtiö"},
            ],
        }
    ],
    "mainBusinessLine": {
        "descriptions": [
            {"languageCode": "1", "description": "Taloustavaroiden vähittäiskauppa"},
        ]
    },
    "addresses": [
        {
            "type": 2,
            "street": "Postal street 1",
            "postCode": "00001",
            "postOffices": [{"languageCode": "1", "city": "POSTALCITY"}],
        },
        {
            "type": 1,
            "street": "Vasaratie 4 A 3",
            "postCode": "65350",
            "postOffices": [
                {"languageCode": "3", "city": "Vaasa (EN)"},
                {"languageCode": "1", "city": "Vaasa"},
            ],
        },
    ],
}

ORG_ROLES = {
    "name": "Activenakusteri Oy",
    "identifier": "0877830-0",
    "complete": True,
    "roles": ["NIMKO"],
}


class FakeRequest:
    def __init__(self, session=None):
        self.session = session if session is not None else {}


class TestOrganizationRolesCompanyResolver:
    def test_returns_name_and_business_id(self):
        request = FakeRequest(session={"organization_roles": ORG_ROLES})
        assert OrganizationRolesCompanyResolver()(request) == {
            "name": "Activenakusteri Oy",
            "business_id": "0877830-0",
        }

    def test_missing_name_defaults_to_empty_string(self):
        request = FakeRequest(session={"organization_roles": {"identifier": "1-2"}})
        assert OrganizationRolesCompanyResolver()(request) == {
            "name": "",
            "business_id": "1-2",
        }

    def test_raises_without_business_id(self):
        request = FakeRequest(session={"organization_roles": {"name": "x"}})
        with pytest.raises(CompanyResolutionError, match="business id"):
            OrganizationRolesCompanyResolver()(request)

    def test_raises_without_organization_roles(self):
        with pytest.raises(CompanyResolutionError, match="business id"):
            OrganizationRolesCompanyResolver()(FakeRequest())


class TestYtjCompanyResolver:
    @pytest.mark.django_db
    def test_parses_preferred_fields(self, requests_mock):
        matcher = re.compile(re.escape(app_settings.YTJ_BASE_URL))
        requests_mock.get(matcher, json={"companies": [DUMMY_YTJ_COMPANY]})

        request = FakeRequest(session={"organization_roles": ORG_ROLES})
        assert YtjCompanyResolver()(request) == {
            "name": "I. Haanpää Oy",
            "business_id": "0877830-0",
            "company_form": "Osakeyhtiö",
            "industry": "Taloustavaroiden vähittäiskauppa",
            "street_address": "Vasaratie 4 A 3",
            "postcode": "65350",
            "city": "Vaasa",
        }

    @pytest.mark.django_db
    def test_falls_back_to_postal_address_and_first_city(self, requests_mock):
        company = {
            "businessId": {"value": "0877830-0"},
            "names": [{"name": "No main name", "type": "2"}],
            "companyForms": [{"type": "OY"}],
            "mainBusinessLine": {},
            "addresses": [
                {
                    "type": 2,
                    "street": "Postal street 1",
                    "postCode": "00001",
                    "postOffices": [{"languageCode": "3", "city": "OnlyEnglish"}],
                }
            ],
        }
        matcher = re.compile(re.escape(app_settings.YTJ_BASE_URL))
        requests_mock.get(matcher, json={"companies": [company]})

        request = FakeRequest(session={"organization_roles": ORG_ROLES})
        assert YtjCompanyResolver()(request) == {
            "name": "No main name",
            "business_id": "0877830-0",
            "company_form": "OY",
            "industry": None,
            "street_address": "Postal street 1",
            "postcode": "00001",
            "city": "OnlyEnglish",
        }

    @pytest.mark.django_db
    def test_missing_address_returns_none_fields(self, requests_mock):
        company = {
            "businessId": {"value": "0877830-0"},
            "names": [{"name": "N", "type": "1"}],
            "companyForms": [],
            "addresses": [],
        }
        matcher = re.compile(re.escape(app_settings.YTJ_BASE_URL))
        requests_mock.get(matcher, json={"companies": [company]})

        request = FakeRequest(session={"organization_roles": ORG_ROLES})
        result = YtjCompanyResolver()(request)
        assert result["company_form"] is None
        assert result["industry"] is None
        assert result["street_address"] is None
        assert result["postcode"] is None
        assert result["city"] is None

    @pytest.mark.django_db
    def test_missing_names_and_post_offices(self, requests_mock):
        company = {
            "businessId": {"value": "0877830-0"},
            "names": [],
            "companyForms": [],
            "addresses": [
                {"type": 1, "street": "Street 1", "postCode": "00001"},
            ],
        }
        matcher = re.compile(re.escape(app_settings.YTJ_BASE_URL))
        requests_mock.get(matcher, json={"companies": [company]})

        request = FakeRequest(session={"organization_roles": ORG_ROLES})
        result = YtjCompanyResolver()(request)
        assert result["name"] == ""
        assert result["street_address"] == "Street 1"
        assert result["city"] is None

    @pytest.mark.django_db
    def test_raises_when_no_company_found(self, requests_mock):
        matcher = re.compile(re.escape(app_settings.YTJ_BASE_URL))
        requests_mock.get(matcher, json={"companies": []})

        request = FakeRequest(session={"organization_roles": ORG_ROLES})
        with pytest.raises(CompanyResolutionError, match="No company found"):
            YtjCompanyResolver()(request)

    @pytest.mark.django_db
    def test_wraps_request_exception(self, requests_mock):
        matcher = re.compile(re.escape(app_settings.YTJ_BASE_URL))
        requests_mock.get(matcher, exc=requests.exceptions.ConnectionError)

        request = FakeRequest(session={"organization_roles": ORG_ROLES})
        with pytest.raises(CompanyResolutionError):
            YtjCompanyResolver()(request)

    def test_raises_when_base_url_unconfigured(self):
        request = FakeRequest(session={"organization_roles": ORG_ROLES})
        with override_settings(SUOMIFI_ON_BEHALF_YTJ_BASE_URL=""):
            with pytest.raises(CompanyResolutionError, match="YTJ_BASE_URL"):
                YtjCompanyResolver()(request)


class TestChainCompanyResolver:
    def test_returns_first_success(self):
        first = mock.Mock(side_effect=CompanyResolutionError("nope"))
        second = mock.Mock(return_value={"business_id": "1-2"})
        third = mock.Mock(return_value={"business_id": "unused"})
        chain = ChainCompanyResolver([first, second, third])

        assert chain(FakeRequest()) == {"business_id": "1-2"}
        third.assert_not_called()

    def test_raises_when_all_fail(self):
        first = mock.Mock(side_effect=CompanyResolutionError("a"))
        second = mock.Mock(side_effect=CompanyResolutionError("b"))
        chain = ChainCompanyResolver([first, second])

        with pytest.raises(
            CompanyResolutionError, match="All company resolvers failed"
        ):
            chain(FakeRequest())


class TestGetCompanyResolver:
    @override_settings(
        SUOMIFI_ON_BEHALF_COMPANY_RESOLVERS=[
            "suomifi_on_behalf.company.OrganizationRolesCompanyResolver"
        ]
    )
    def test_single_entry_returns_resolver_directly(self):
        assert isinstance(get_company_resolver(), OrganizationRolesCompanyResolver)

    @override_settings(
        SUOMIFI_ON_BEHALF_COMPANY_RESOLVERS=[
            "suomifi_on_behalf.company.YtjCompanyResolver",
            "suomifi_on_behalf.company.OrganizationRolesCompanyResolver",
        ]
    )
    def test_multiple_entries_are_chained(self):
        resolver = get_company_resolver()
        assert isinstance(resolver, ChainCompanyResolver)
        assert [type(r) for r in resolver.resolvers] == [
            YtjCompanyResolver,
            OrganizationRolesCompanyResolver,
        ]

    def test_accepts_plain_callable_entry(self):
        def my_resolver(request):
            return {"business_id": "1-2"}

        with override_settings(SUOMIFI_ON_BEHALF_COMPANY_RESOLVERS=[my_resolver]):
            assert get_company_resolver()(FakeRequest()) == {"business_id": "1-2"}

    @override_settings(SUOMIFI_ON_BEHALF_COMPANY_RESOLVERS=None)
    def test_raises_when_unconfigured(self):
        with pytest.raises(
            ImproperlyConfigured, match="SUOMIFI_ON_BEHALF_COMPANY_RESOLVERS"
        ):
            get_company_resolver()

    @override_settings(SUOMIFI_ON_BEHALF_COMPANY_RESOLVERS=[object()])
    def test_raises_when_entry_not_callable(self):
        with pytest.raises(ImproperlyConfigured, match="not callable"):
            get_company_resolver()


class TestGetCompany:
    @pytest.mark.django_db
    def test_returns_cached_company(self, session_request):
        session_request.session["company"] = {"business_id": "cached"}
        assert get_company(session_request) == {"business_id": "cached"}

    @pytest.mark.django_db
    def test_resolves_via_ytj_and_caches_and_signals(
        self, session_request, requests_mock
    ):
        session_request.session["organization_roles"] = ORG_ROLES
        matcher = re.compile(re.escape(app_settings.YTJ_BASE_URL))
        requests_mock.get(matcher, json={"companies": [DUMMY_YTJ_COMPANY]})

        received = []

        def handler(sender, **kwargs):
            received.append(kwargs)

        suomifi_company_resolved.connect(handler)
        try:
            company = get_company(session_request)
        finally:
            suomifi_company_resolved.disconnect(handler)

        assert company["business_id"] == "0877830-0"
        assert company["name"] == "I. Haanpää Oy"
        assert session_request.session["company"] == company
        assert received and received[0]["company"] == company

    @pytest.mark.django_db
    def test_falls_back_to_organization_roles_when_ytj_fails(
        self, session_request, requests_mock
    ):
        session_request.session["organization_roles"] = ORG_ROLES
        matcher = re.compile(re.escape(app_settings.YTJ_BASE_URL))
        requests_mock.get(matcher, text="Error", status_code=404)

        company = get_company(session_request)

        assert company == {"name": "Activenakusteri Oy", "business_id": "0877830-0"}

    @pytest.mark.django_db
    @override_settings(
        SUOMIFI_ON_BEHALF_COMPANY_RESOLVERS=[
            "suomifi_on_behalf.company.YtjCompanyResolver"
        ]
    )
    def test_emits_failure_signal_and_raises(self, session_request, requests_mock):
        session_request.session["organization_roles"] = ORG_ROLES
        matcher = re.compile(re.escape(app_settings.YTJ_BASE_URL))
        requests_mock.get(matcher, text="Error", status_code=500)

        received = []

        def handler(sender, **kwargs):
            received.append(kwargs)

        suomifi_company_resolution_failed.connect(handler)
        try:
            with pytest.raises(CompanyResolutionError):
                get_company(session_request)
        finally:
            suomifi_company_resolution_failed.disconnect(handler)

        assert received and "error" in received[0]

    @pytest.mark.django_db
    def test_raises_when_mandate_missing_from_session(self, session_request):
        # get_company operates on the session mandate and does not fetch it; with no
        # organization_roles present, every resolver fails with no network calls.
        with pytest.raises(CompanyResolutionError):
            get_company(session_request)

    @pytest.mark.django_db
    def test_use_cache_false_bypasses_read_and_write_and_signals(
        self, session_request, requests_mock
    ):
        # A stale cached value must be ignored, the resolver must run, and the session
        # must not be written when caching is bypassed for the call.
        session_request.session["company"] = {"business_id": "stale"}
        session_request.session["organization_roles"] = ORG_ROLES
        matcher = re.compile(re.escape(app_settings.YTJ_BASE_URL))
        requests_mock.get(matcher, json={"companies": [DUMMY_YTJ_COMPANY]})

        received = []

        def handler(sender, **kwargs):
            received.append(kwargs)

        suomifi_company_resolved.connect(handler)
        try:
            company = get_company(session_request, use_cache=False)
        finally:
            suomifi_company_resolved.disconnect(handler)

        assert company["business_id"] == "0877830-0"
        assert session_request.session["company"] == {"business_id": "stale"}
        assert received and received[0]["company"] == company

    @pytest.mark.django_db
    @override_settings(SUOMIFI_ON_BEHALF_CACHE_COMPANY_IN_SESSION=False)
    def test_setting_disables_cache_for_default_calls(
        self, session_request, requests_mock
    ):
        session_request.session["organization_roles"] = ORG_ROLES
        matcher = re.compile(re.escape(app_settings.YTJ_BASE_URL))
        requests_mock.get(matcher, json={"companies": [DUMMY_YTJ_COMPANY]})

        received = []

        def handler(sender, **kwargs):
            received.append(kwargs)

        suomifi_company_resolved.connect(handler)
        try:
            company = get_company(session_request)
        finally:
            suomifi_company_resolved.disconnect(handler)

        assert company["business_id"] == "0877830-0"
        assert "company" not in session_request.session
        assert received and received[0]["company"] == company

    @pytest.mark.django_db
    @override_settings(SUOMIFI_ON_BEHALF_CACHE_COMPANY_IN_SESSION=False)
    def test_explicit_use_cache_true_overrides_disabled_setting(
        self, session_request, requests_mock
    ):
        session_request.session["organization_roles"] = ORG_ROLES
        matcher = re.compile(re.escape(app_settings.YTJ_BASE_URL))
        requests_mock.get(matcher, json={"companies": [DUMMY_YTJ_COMPANY]})

        company = get_company(session_request, use_cache=True)

        assert session_request.session["company"] == company

    @pytest.mark.django_db
    @override_settings(
        SUOMIFI_ON_BEHALF_COMPANY_RESOLVERS=[
            "suomifi_on_behalf.company.YtjCompanyResolver"
        ]
    )
    def test_failure_signal_fires_with_cache_bypassed(
        self, session_request, requests_mock
    ):
        session_request.session["organization_roles"] = ORG_ROLES
        matcher = re.compile(re.escape(app_settings.YTJ_BASE_URL))
        requests_mock.get(matcher, text="Error", status_code=500)

        received = []

        def handler(sender, **kwargs):
            received.append(kwargs)

        suomifi_company_resolution_failed.connect(handler)
        try:
            with pytest.raises(CompanyResolutionError):
                get_company(session_request, use_cache=False)
        finally:
            suomifi_company_resolution_failed.disconnect(handler)

        assert received and "error" in received[0]
