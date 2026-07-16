from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string
from requests.exceptions import RequestException

from suomifi_on_behalf import app_settings
from suomifi_on_behalf.client import SignedUserinfoNotSupportedError, get_userinfo
from suomifi_on_behalf.helsinki_profile import (
    HelsinkiProfileClient,
    HelsinkiProfileError,
)


class SsnResolutionError(Exception):
    """
    Raised when a resolver cannot produce a national identification number.

    The eAuthorizations request view catches this and redirects the user to the
    login failure page instead of raising.
    """


class OidcUserinfoSsnResolver:
    """
    Resolve the SSN from an OIDC userinfo claim.

    Subclass and override `claim` to match your identity provider's claim name.
    """

    claim = "national_id_num"

    def __call__(self, request) -> str:
        if not request.session.get("oidc_access_token"):
            raise SsnResolutionError("Missing oidc_access_token in session")
        try:
            userinfo = get_userinfo(request)
        except (SignedUserinfoNotSupportedError, RequestException) as e:
            raise SsnResolutionError(str(e)) from e
        ssn = userinfo.get(self.claim)
        if not ssn:
            raise SsnResolutionError(f"No {self.claim!r} claim in userinfo response")
        return ssn


class HelsinkiProfileSsnResolver:
    """
    Resolve the SSN from the Helsinki Profile GraphQL API.

    Reads `verifiedPersonalInformation.nationalIdentificationNumber` using the
    OIDC access token stored in the session.
    """

    def __call__(self, request) -> str:
        access_token = request.session.get("oidc_access_token")
        if not access_token:
            raise SsnResolutionError("Missing oidc_access_token in session")
        try:
            ssn = HelsinkiProfileClient().get_profile(access_token).get("user_ssn")
        except HelsinkiProfileError as e:
            raise SsnResolutionError(str(e)) from e
        if not ssn:
            raise SsnResolutionError("Helsinki Profile returned no SSN")
        return ssn


class ChainSsnResolver:
    """
    Try each resolver in order and return the first successfully resolved SSN.

    Raises `SsnResolutionError` only if every resolver fails.
    """

    def __init__(self, resolvers):
        self.resolvers = list(resolvers)

    def __call__(self, request) -> str:
        errors = []
        for resolver in self.resolvers:
            try:
                return resolver(request)
            except SsnResolutionError as e:
                errors.append(f"{type(resolver).__name__}: {e}")
        raise SsnResolutionError("All SSN resolvers failed: " + "; ".join(errors))


def _load_resolver(entry):
    obj = import_string(entry) if isinstance(entry, str) else entry
    if isinstance(obj, type):
        obj = obj()
    if not callable(obj):
        raise ImproperlyConfigured(f"SSN resolver {entry!r} is not callable")
    return obj


def get_ssn_resolver():
    """
    Build the configured SSN resolver from `SUOMIFI_ON_BEHALF_SSN_RESOLVERS`.

    The setting is a list of dotted paths (or objects). Each entry is a callable
    taking the request and returning the SSN, or a class instantiated with no
    arguments. A single entry is used directly; multiple entries are wrapped in a
    `ChainSsnResolver` and tried in order.
    """
    configured = app_settings.SSN_RESOLVERS
    if not configured:
        raise ImproperlyConfigured(
            "SUOMIFI_ON_BEHALF_SSN_RESOLVERS must list at least one SSN resolver."
        )
    resolvers = [_load_resolver(entry) for entry in configured]
    return resolvers[0] if len(resolvers) == 1 else ChainSsnResolver(resolvers)
