import logging
from urllib.parse import urlencode
from uuid import uuid4

import requests
from django.conf import settings
from django.contrib import auth
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from requests.auth import HTTPBasicAuth
from requests.exceptions import HTTPError

from suomifi_on_behalf import app_settings
from suomifi_on_behalf.client import get_checksum_header
from suomifi_on_behalf.sessions import (
    get_eauth_login_success_url,
    store_token_info_in_eauth_session,
    validate_login_success_url,
)
from suomifi_on_behalf.ssn import SsnResolutionError, get_ssn_resolver

logger = logging.getLogger(__name__)


class EauthAuthenticationRequestView(View):
    """
    Eauth client authentication HTTP endpoint.

    Docs that describe the flow (only in Finnish):
    https://palveluhallinta.suomi.fi/fi/tuki/artikkelit/592d774503f6d100018db5dd
    """

    http_method_names = ["get"]

    def login_failure(self):
        return HttpResponseRedirect(app_settings.LOGIN_ERROR_URL)

    def register_user(self, person_id):
        """
        Start a Suomi.fi Valtuudet Web API session for the given person.

        Sends the registration request ("Web API -session aloitus eli
        rekisteröintipyyntö") and returns the response, which contains the `sessionId`
        and `userId` used to continue the eAuthorizations flow.

        Docs (only in Finnish):
        https://palveluhallinta.suomi.fi/fi/tuki/artikkelit/592d774503f6d100018db5dd
        """
        request_id = uuid4()
        path = (
            f"/service/ypa/user/register/{app_settings.EAUTHORIZATIONS_CLIENT_ID}"
            f"/{person_id}?requestId={request_id}"
        )

        checksum_header = get_checksum_header(path)

        response = requests.get(
            app_settings.EAUTHORIZATIONS_BASE_URL + path,
            headers={
                "X-AsiointivaltuudetAuthorization": checksum_header,
            },
        )
        response.raise_for_status()
        return response.json()

    def get(self, request):
        """
        Eauth client authentication initialization HTTP endpoint.

        NOTE: We should avoid raising exceptions from the method, because it results in
        user's auth flow ending on Django's 500 error page. We should instead call
        `self.login_failure()` to redirect the user to the login error page in the UI.
        A missing success URL is the one exception: that is a deployment error rather
        than an auth failure, so it is raised instead of hidden behind the error page.
        """
        # Checked here because it is otherwise only read at the end of the callback.
        validate_login_success_url()

        try:
            user_ssn = get_ssn_resolver()(request)
        except SsnResolutionError as e:
            logger.error("Cannot use eauthorizations API: %s", e)
            return self.login_failure()

        register_info = self.register_user(user_ssn)

        session_id = register_info.get("sessionId")
        user_id = register_info.get("userId")

        store_token_info_in_eauth_session(request, {"id_token": session_id})

        auth_url = app_settings.EAUTHORIZATIONS_BASE_URL + "/oauth/authorize"

        params = {
            "client_id": app_settings.EAUTHORIZATIONS_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": (
                request.build_absolute_uri(
                    reverse("eauth_authentication_callback")
                ).replace("http://", "https://")
            ),
            "user": user_id,
        }

        lang = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        if lang:
            params["lang"] = lang

        query = urlencode(params)

        redirect_url = f"{auth_url}?{query}"

        return HttpResponseRedirect(redirect_url)


class EauthAuthenticationCallbackView(View):
    """
    Eauth client callback HTTP endpoint.
    """

    http_method_names = ["get"]

    def login_success(self):
        url = get_eauth_login_success_url(self.request)

        lang = self.request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        if lang:
            url = f"{url.rstrip('/')}/{lang}/"

        return HttpResponseRedirect(url)

    def login_failure(self):
        """
        Redirect the user to the login failure page, appending the current language
        from cookies to the redirect URL path if available.
        """
        url, error_path = app_settings.LOGIN_ERROR_URL.rsplit("/", 1)

        lang = self.request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        if lang:
            url = f"{url}/{lang}/{error_path}"

        return HttpResponseRedirect(url)

    def get_token_info(self, code):
        """
        Return token object as a dictionary.
        """
        auth_header = HTTPBasicAuth(
            app_settings.EAUTHORIZATIONS_CLIENT_ID,
            app_settings.EAUTHORIZATIONS_API_OAUTH_SECRET,
        )

        token_endpoint_url = app_settings.EAUTHORIZATIONS_BASE_URL + "/oauth/token"

        params = {
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": (
                self.request.build_absolute_uri(
                    reverse("eauth_authentication_callback")
                ).replace("http://", "https://")
            ),
        }
        query = urlencode(params)

        token_url = f"{token_endpoint_url}?{query}"
        response = requests.post(
            token_url,
            auth=auth_header,
        )
        response.raise_for_status()

        return response.json()

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        """
        Eauth client authentication callback HTTP endpoint.
        """
        if request.GET.get("error"):
            if request.user.is_authenticated:
                auth.logout(request)
            assert not request.user.is_authenticated
            logger.error(str(request.GET["error"]))
        elif "code" in request.GET:
            try:
                token_info = self.get_token_info(request.GET["code"])
                store_token_info_in_eauth_session(request, token_info)

                # Store organization roles in session
                from suomifi_on_behalf.client import request_organization_roles

                request_organization_roles(request)
            except HTTPError as e:
                logger.error(str(e))
                return self.login_failure()
            return self.login_success()
        return self.login_failure()
