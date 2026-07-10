import base64
import hashlib
import hmac
from uuid import uuid4

import requests
from django.http import HttpRequest
from django.utils import timezone
from requests.exceptions import RequestException

from suomifi_on_behalf import app_settings
from suomifi_on_behalf.signals import (
    suomifi_mandate_queried,
    suomifi_mandate_query_failed,
)


class SignedUserinfoNotSupportedError(Exception):
    """
    Raised when the OIDC userinfo endpoint returns a signed JWT response.

    This library only reads plain JSON userinfo. Verifying a signed
    (`application/jwt`) userinfo response would require JWKS handling and a JWT
    dependency, which is out of scope; use a custom SSN resolver instead.
    """


def get_userinfo(request: HttpRequest) -> dict:
    """
    Fetch the OIDC userinfo claims for the currently stored access token.

    Performs a bearer-authenticated GET against
    `SUOMIFI_ON_BEHALF_OIDC_USERINFO_ENDPOINT`. The request mechanics (bearer header,
    `verify` / `timeout` / `proxies`, `raise_for_status`) match
    `mozilla_django_oidc` 4.0.1's `get_userinfo`, but the knobs are read from this
    library's namespaced `SUOMIFI_ON_BEHALF_OIDC_*` settings and no dependency on that
    package or a full OIDC authentication backend is required.

    Only plain JSON userinfo is supported. If the endpoint returns a signed JWT
    (`content-type: application/jwt`), `SignedUserinfoNotSupportedError` is raised;
    provide a custom SSN resolver to verify and decode it.
    """
    access_token = request.session.get("oidc_access_token")
    response = requests.get(
        app_settings.OIDC_USERINFO_ENDPOINT,
        headers={"Authorization": f"Bearer {access_token}"},
        verify=app_settings.OIDC_VERIFY_SSL,
        timeout=app_settings.OIDC_TIMEOUT,
        proxies=app_settings.OIDC_PROXY,
    )
    response.raise_for_status()

    content_type = response.headers.get("content-type", "").lower()
    if content_type.startswith("application/jwt"):
        raise SignedUserinfoNotSupportedError(
            "The OIDC userinfo endpoint returned a signed JWT "
            "(content-type: application/jwt), which this library does not verify. "
            "Return a plain JSON userinfo response, or configure a custom resolver "
            "in SUOMIFI_ON_BEHALF_SSN_RESOLVERS."
        )

    return response.json()


def get_checksum_header(path: str) -> str:
    """
    Build the custom checksum header required by the Suomi.fi Valtuudet API.

    Docs (only in Finnish), search for "4.3 Tarkistesumman laskeminen":
    https://palveluhallinta.suomi.fi/fi/tuki/artikkelit/5a781dc75cb4f10dde9735e4
    """
    timestamp = timezone.now().isoformat()
    message = f"{path} {timestamp}"

    byte_secret = app_settings.EAUTHORIZATIONS_CLIENT_SECRET.encode()
    byte_message = message.encode()

    hash_result = hmac.new(byte_secret, byte_message, hashlib.sha256)
    checksum = base64.b64encode(hash_result.digest()).decode()
    return f"{app_settings.EAUTHORIZATIONS_CLIENT_ID} {timestamp} {checksum}"


def request_organization_roles(request: HttpRequest) -> dict:
    """
    Query Suomi.fi mandates ("Valtuudet") for organization roles for the authenticated
    user.

    This function queries the Suomi.fi Valtuudet (eAuthorizations) REST API to
    verify that the user holds a valid mandate for a company and to retrieve
    the list of roles granted. On success the roles are stored in the session and the
    `suomifi_mandate_queried` signal is emitted.

    :param request: The HttpRequest containing the current session.
    :return: The user's organization roles.
    """
    request_id = uuid4()
    id_token = request.session.get("eauth_id_token")
    path = f"/service/ypa/api/organizationRoles/{id_token}?requestId={request_id}"
    organization_roles_endpoint = f"{app_settings.EAUTHORIZATIONS_BASE_URL}{path}"

    checksum_header = get_checksum_header(path)

    eauth_access_token = request.session.get("eauth_access_token")

    try:
        response = requests.get(
            organization_roles_endpoint,
            headers={
                "Authorization": f"Bearer {eauth_access_token}",
                "X-AsiointivaltuudetAuthorization": checksum_header,
            },
        )
        response.raise_for_status()
    except RequestException as e:
        suomifi_mandate_query_failed.send(
            sender=request_organization_roles,
            request=request,
            request_id=str(request_id),
            error=e,
        )
        raise

    org_roles = response.json()[0]

    suomifi_mandate_queried.send(
        sender=request_organization_roles,
        request=request,
        request_id=str(request_id),
        organization_roles=org_roles,
    )

    if request:
        request.session["organization_roles"] = org_roles

    return org_roles


def get_organization_roles(request: HttpRequest) -> dict:
    """
    Return the user's Suomi.fi organization roles ("Valtuudet").

    Reads the cached `organization_roles` from the session and, if absent, fetches
    them once via `request_organization_roles` (which also stores them and emits the
    `suomifi_mandate_queried` signal).

    :param request: The HttpRequest containing the current session.
    :return: The user's organization roles.
    """
    org_roles = request.session.get("organization_roles")

    if not org_roles:
        org_roles = request_organization_roles(request)

    return org_roles
