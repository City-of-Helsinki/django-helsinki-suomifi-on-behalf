from datetime import timedelta

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from suomifi_on_behalf import app_settings


def is_safe_redirect_url(
    request: HttpRequest,
    url: str,
    allowed_hosts: list | None = None,
    require_https: bool | None = None,
) -> bool:
    """
    Check if the given URL is safe for redirecting.

    When `allowed_hosts` / `require_https` are not given, they fall back to
    `SUOMIFI_ON_BEHALF_REDIRECT_ALLOWED_HOSTS` /
    `SUOMIFI_ON_BEHALF_REDIRECT_REQUIRE_HTTPS` (and finally to
    `request.is_secure()` when the latter is unset).
    """
    if not url:
        return False

    if allowed_hosts is None:
        allowed_hosts = app_settings.REDIRECT_ALLOWED_HOSTS

    if require_https is None:
        require_https = app_settings.REDIRECT_REQUIRE_HTTPS
        if require_https is None:
            require_https = request.is_secure()

    all_allowed_hosts = list(allowed_hosts)
    all_allowed_hosts.append(request.get_host())

    return url_has_allowed_host_and_scheme(
        url=url,
        allowed_hosts=all_allowed_hosts,
        require_https=require_https,
    )


def validate_login_success_url() -> None:
    """
    Assert that the post-login destination is configured.

    :raises ImproperlyConfigured: when `SUOMIFI_ON_BEHALF_LOGIN_SUCCESS_URL` is unset.
    """
    if not app_settings.LOGIN_SUCCESS_URL:
        raise ImproperlyConfigured(
            "SUOMIFI_ON_BEHALF_LOGIN_SUCCESS_URL must be set to the URL the user is "
            "redirected to after a successful login."
        )


def get_eauth_login_success_url(request: HttpRequest) -> str:
    """
    Determine the redirect URL after a successful eAuthorizations or Helsinki Profile
    login.

    This function supports dynamic redirects by checking the user's session for
    an 'eauth_next_url'. This allows the authentication flow to return the user back
    to the exact URL they originated from, rather than a hardcoded fallback.

    If no safe 'eauth_next_url' is found in the session, the function uses
    `SUOMIFI_ON_BEHALF_LOGIN_SUCCESS_URL`.

    :param request: The HttpRequest containing the current session.
    :return: A string representing the URL to redirect the user to.
    :raises ImproperlyConfigured: when there is no safe session URL and
        `SUOMIFI_ON_BEHALF_LOGIN_SUCCESS_URL` is unset.
    """
    next_url = request.session.pop("eauth_next_url", None)

    if next_url and is_safe_redirect_url(request, next_url):
        return next_url

    validate_login_success_url()

    return str(app_settings.LOGIN_SUCCESS_URL)


def store_token_info_in_session(request: HttpRequest, token_info: dict, prefix=""):
    session_dict = {}

    if id_token := token_info.get("id_token"):
        session_dict[f"{prefix}_id_token"] = id_token

    if access_token := token_info.get("access_token"):
        session_dict[f"{prefix}_access_token"] = access_token

    if access_token_expires := token_info.get("expires_in"):
        session_dict[f"{prefix}_access_token_expires"] = (
            timezone.now()
            + timedelta(seconds=access_token_expires - 5)  # Add a bit of headroom
        ).isoformat()

    if refresh_token := token_info.get("refresh_token"):
        session_dict[f"{prefix}_refresh_token"] = refresh_token

    if refresh_token_expires := token_info.get("refresh_expires_in"):
        session_dict[f"{prefix}_refresh_token_expires"] = (
            timezone.now()
            + timedelta(seconds=refresh_token_expires - 5)  # Add a bit of headroom
        ).isoformat()

    request.session.update(session_dict)

    return session_dict


def store_token_info_in_eauth_session(
    request: HttpRequest,
    token_info: dict,
) -> dict:
    """
    Store token info in the session and return the values as dict.
    """
    return store_token_info_in_session(request, token_info, "eauth")
