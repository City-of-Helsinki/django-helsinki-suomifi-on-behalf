# ruff: noqa: N802 - uppercase property names match Django setting conventions
from typing import TYPE_CHECKING

from django.conf import settings as django_settings

if TYPE_CHECKING:
    # eAuthorizations (Valtuudet)
    EAUTHORIZATIONS_BASE_URL: str
    EAUTHORIZATIONS_CLIENT_ID: str
    EAUTHORIZATIONS_CLIENT_SECRET: str
    EAUTHORIZATIONS_API_OAUTH_SECRET: str

    # SSN (hetu) resolution
    SSN_RESOLVERS: list | None

    # Redirects
    LOGIN_ERROR_URL: str
    REDIRECT_ALLOWED_HOSTS: list
    REDIRECT_REQUIRE_HTTPS: bool | None

    # OIDC userinfo (used by OidcUserinfoSsnResolver)
    OIDC_USERINFO_ENDPOINT: str
    OIDC_VERIFY_SSL: bool
    OIDC_TIMEOUT: float | None
    OIDC_PROXY: dict | None

    # Helsinki Profile (used by HelsinkiProfileSsnResolver)
    HELSINKI_PROFILE_API_URL: str
    HELSINKI_PROFILE_SCOPE: str
    TUNNISTUS_API_TOKENS_ENDPOINT: str


class SuomiFiOnBehalfSettings:
    """
    Namespaced access to this library's Django settings.

    Every setting is read from `django.conf.settings` under the `SUOMIFI_ON_BEHALF_`
    prefix and has a default, so access is lazy and overridable in tests. Standard
    Django settings the library also relies on (`LOGIN_REDIRECT_URL`,
    `LANGUAGE_COOKIE_NAME`) are read directly and are not exposed here.
    """

    prefix = "SUOMIFI_ON_BEHALF_"

    def _setting(self, name: str, default):
        return getattr(django_settings, self.prefix + name, default)

    # eAuthorizations (Valtuudet)

    @property
    def EAUTHORIZATIONS_BASE_URL(self) -> str:
        return self._setting("EAUTHORIZATIONS_BASE_URL", "")

    @property
    def EAUTHORIZATIONS_CLIENT_ID(self) -> str:
        return self._setting("EAUTHORIZATIONS_CLIENT_ID", "")

    @property
    def EAUTHORIZATIONS_CLIENT_SECRET(self) -> str:
        return self._setting("EAUTHORIZATIONS_CLIENT_SECRET", "")

    @property
    def EAUTHORIZATIONS_API_OAUTH_SECRET(self) -> str:
        return self._setting("EAUTHORIZATIONS_API_OAUTH_SECRET", "")

    # SSN (hetu) resolution

    @property
    def SSN_RESOLVERS(self) -> list | None:
        return self._setting("SSN_RESOLVERS", None)

    # Redirects

    @property
    def LOGIN_ERROR_URL(self) -> str:
        return self._setting("LOGIN_ERROR_URL", "")

    @property
    def REDIRECT_ALLOWED_HOSTS(self) -> list:
        return self._setting("REDIRECT_ALLOWED_HOSTS", [])

    @property
    def REDIRECT_REQUIRE_HTTPS(self) -> bool | None:
        # None means "not configured"; callers fall back to request.is_secure().
        return self._setting("REDIRECT_REQUIRE_HTTPS", None)

    # OIDC userinfo (used by OidcUserinfoSsnResolver)

    @property
    def OIDC_USERINFO_ENDPOINT(self) -> str:
        return self._setting("OIDC_USERINFO_ENDPOINT", "")

    @property
    def OIDC_VERIFY_SSL(self) -> bool:
        return self._setting("OIDC_VERIFY_SSL", True)

    @property
    def OIDC_TIMEOUT(self) -> float | None:
        return self._setting("OIDC_TIMEOUT", None)

    @property
    def OIDC_PROXY(self) -> dict | None:
        return self._setting("OIDC_PROXY", None)

    # Helsinki Profile (used by HelsinkiProfileSsnResolver)

    @property
    def HELSINKI_PROFILE_API_URL(self) -> str:
        return self._setting("HELSINKI_PROFILE_API_URL", "")

    @property
    def HELSINKI_PROFILE_AUDIENCE(self) -> str:
        return self._setting("HELSINKI_PROFILE_AUDIENCE", "")

    @property
    def HELSINKI_PROFILE_SCOPE(self) -> str:
        return self._setting("HELSINKI_PROFILE_SCOPE", "")

    @property
    def TUNNISTUS_API_TOKENS_ENDPOINT(self) -> str:
        return self._setting("TUNNISTUS_API_TOKENS_ENDPOINT", "")


_settings = SuomiFiOnBehalfSettings()


def __getattr__(name: str):
    # See https://peps.python.org/pep-0562/
    return getattr(_settings, name)
