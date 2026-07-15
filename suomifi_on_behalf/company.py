import requests
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string
from requests.exceptions import RequestException

from suomifi_on_behalf import app_settings
from suomifi_on_behalf.signals import (
    suomifi_company_resolution_failed,
    suomifi_company_resolved,
)

# Language codes returned by the YTJ API, in the order this library prefers them
# (Finnish first, then Swedish). See https://avoindata.prh.fi/fi/ytj/swagger-ui.
_PREFERRED_LANGS = ("1", "2")


class CompanyResolutionError(Exception):
    """
    Raised when a resolver cannot produce company data.

    `get_company` catches this from a resolver, emits
    `suomifi_company_resolution_failed`, and re-raises it.
    """


def _get_business_id(request) -> str:
    """
    Read the company business id (``identifier``) from the mandate stored in the
    session by the eAuthorizations flow.
    """
    roles = request.session.get("organization_roles") or {}
    business_id = roles.get("identifier")
    if not isinstance(business_id, str) or not business_id:
        raise CompanyResolutionError(
            "No business id ('identifier') in session organization_roles"
        )
    return business_id


class OrganizationRolesCompanyResolver:
    """
    Resolve company data from the Suomi.fi mandate already in the session.

    Performs no external calls: returns only the ``name`` and ``business_id`` carried
    by the organization roles. Intended as the terminal fallback in a resolver chain.
    """

    def __call__(self, request) -> dict:
        roles = request.session.get("organization_roles") or {}
        business_id = _get_business_id(request)
        return {"name": roles.get("name") or "", "business_id": business_id}


class YtjCompanyResolver:
    """
    Resolve company data from the YTJ (avoindata PRH v3) open data API.

    Looks the company up by the mandate's business id and returns the preferred
    (Finnish, then Swedish) name, company form, industry and address. Raises
    `CompanyResolutionError` when the API is unavailable or returns no company, so a
    chain can fall through to another resolver.
    """

    def __call__(self, request) -> dict:
        business_id = _get_business_id(request)
        base_url = app_settings.YTJ_BASE_URL
        if not base_url:
            raise CompanyResolutionError(
                "SUOMIFI_ON_BEHALF_YTJ_BASE_URL is not configured"
            )
        try:
            response = requests.get(
                f"{base_url}/companies",
                params={"businessId": business_id},
                timeout=app_settings.YTJ_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
        except RequestException as e:
            raise CompanyResolutionError(str(e)) from e

        companies = data.get("companies") if isinstance(data, dict) else None
        if not companies:
            raise CompanyResolutionError(
                f"No company found in YTJ for business id {business_id}"
            )
        return _parse_ytj_company(companies[0], business_id)


def _preferred_description(descriptions) -> str | None:
    by_lang = {d.get("languageCode"): d.get("description") for d in descriptions or []}
    for lang in _PREFERRED_LANGS:
        if by_lang.get(lang):
            return by_lang[lang]
    return None


def _preferred_city(post_offices) -> str | None:
    by_lang = {po.get("languageCode"): po.get("city") for po in post_offices or []}
    for lang in _PREFERRED_LANGS:
        if by_lang.get(lang):
            return by_lang[lang]
    if post_offices:
        return post_offices[0].get("city")
    return None


def _preferred_name(names) -> str | None:
    # Company name: prefer the main name (type "1"), fall back to the first available.
    main = next(
        (n.get("name") for n in names or [] if n.get("type") == "1" and n.get("name")),
        None,
    )
    if main:
        return main
    if names:
        return names[0].get("name")
    return None


def _company_form(company_forms) -> str | None:
    if not company_forms:
        return None
    form = company_forms[0]
    return _preferred_description(form.get("descriptions")) or form.get("type")


def _address(addresses) -> dict:
    # YTJ address types: 1 is the visiting address, 2 is the postal address.
    visiting = next((a for a in addresses or [] if a.get("type") == 1), None)
    postal = next((a for a in addresses or [] if a.get("type") == 2), None)
    address = visiting or postal
    if not address:
        return {"street_address": None, "postcode": None, "city": None}
    return {
        "street_address": address.get("street"),
        "postcode": address.get("postCode"),
        "city": _preferred_city(address.get("postOffices")),
    }


def _parse_ytj_company(company: dict, business_id: str) -> dict:
    """
    Extract the fields this library exposes from a single YTJ v3 company object.

    Missing optional fields are returned as ``None`` (or ``""`` for the name) rather
    than raising, leaving it to the caller to decide how to handle partial data.
    """
    return {
        "name": _preferred_name(company.get("names")) or "",
        "business_id": business_id,
        "company_form": _company_form(company.get("companyForms")),
        "industry": _preferred_description(
            (company.get("mainBusinessLine") or {}).get("descriptions")
        ),
        **_address(company.get("addresses")),
    }


class ChainCompanyResolver:
    """
    Try each resolver in order and return the first successfully resolved company.

    Raises `CompanyResolutionError` only if every resolver fails.
    """

    def __init__(self, resolvers):
        self.resolvers = list(resolvers)

    def __call__(self, request) -> dict:
        errors = []
        for resolver in self.resolvers:
            try:
                return resolver(request)
            except CompanyResolutionError as e:
                errors.append(f"{type(resolver).__name__}: {e}")
        raise CompanyResolutionError(
            "All company resolvers failed: " + "; ".join(errors)
        )


def _load_resolver(entry):
    obj = import_string(entry) if isinstance(entry, str) else entry
    if isinstance(obj, type):
        obj = obj()
    if not callable(obj):
        raise ImproperlyConfigured(f"Company resolver {entry!r} is not callable")
    return obj


def get_company_resolver():
    """
    Build the configured company resolver from `SUOMIFI_ON_BEHALF_COMPANY_RESOLVERS`.

    The setting is a list of dotted paths (or objects). Each entry is a callable
    taking the request and returning a company dict, or a class instantiated with no
    arguments. A single entry is used directly; multiple entries are wrapped in a
    `ChainCompanyResolver` and tried in order.
    """
    configured = app_settings.COMPANY_RESOLVERS
    if not configured:
        raise ImproperlyConfigured(
            "SUOMIFI_ON_BEHALF_COMPANY_RESOLVERS must list at least one "
            "company resolver."
        )
    resolvers = [_load_resolver(entry) for entry in configured]
    return resolvers[0] if len(resolvers) == 1 else ChainCompanyResolver(resolvers)


def get_company(request) -> dict:
    """
    Return the authenticated user's company data as a dict.

    Reads the cached ``company`` from the session and, if absent, runs the configured
    company resolver chain over the mandate stored in the session by the
    eAuthorizations flow, caches the result, and emits `suomifi_company_resolved`. On
    failure it emits `suomifi_company_resolution_failed` and raises
    `CompanyResolutionError`.

    The mandate ("organization roles") must already be in the session; the
    eAuthorizations callback stores it. This function does not fetch it.

    This library only returns the data; persisting a company record is left to the
    consuming application.

    :param request: The HttpRequest containing the current session.
    :return: The user's company data.
    """
    company = request.session.get("company")
    if company:
        return company

    resolver = get_company_resolver()
    try:
        company = resolver(request)
    except CompanyResolutionError as error:
        suomifi_company_resolution_failed.send(
            sender=get_company, request=request, error=error
        )
        raise

    request.session["company"] = company
    suomifi_company_resolved.send(sender=get_company, request=request, company=company)
    return company
