import requests
from requests import RequestException

from suomifi_on_behalf import app_settings


class HelsinkiProfileError(Exception):
    """
    Common class for exceptions raised by `HelsinkiProfileClient`
    """


class HelsinkiProfileClient:
    """
    Client for reading data from the Helsinki Profile GraphQL API.

    https://helsinkisolutionoffice.atlassian.net/wiki/spaces/KAN/pages/6172606574/Full+Helsinki-profile+with+citizen+profile+and+API+authorization+support+features
    """

    def __init__(self):
        if not all(
            [
                app_settings.TUNNISTUS_API_TOKENS_ENDPOINT,
                app_settings.HELSINKI_PROFILE_API_URL,
                app_settings.HELSINKI_PROFILE_AUDIENCE,
                app_settings.HELSINKI_PROFILE_SCOPE,
            ]
        ):
            raise HelsinkiProfileError("HelsinkiProfileClient settings not configured.")

    def get_profile(self, oidc_access_token):
        """
        Reads user's profile from the API.

        Currently only reads the `nationalIdentificationNumber`, but can easily be
        modified to read other data if needed.

        :raises HelsinkiProfileError if profile cannot be successfully read

        :return dict with queried values (value may be `None`)
        """

        api_access_token = self.get_api_access_token(oidc_access_token)

        try:
            payload = {
                "query": (
                    """
                    query myProfile {
                        myProfile {
                            verifiedPersonalInformation {
                                nationalIdentificationNumber
                            }
                        }
                    }
                """
                ),
            }
            response = requests.post(
                app_settings.HELSINKI_PROFILE_API_URL,
                json=payload,
                timeout=10,
                verify=True,
                headers={"Authorization": "Bearer " + api_access_token},
            )
            response.raise_for_status()
        except RequestException as e:
            raise HelsinkiProfileError(str(e))

        profile_data = response.json()

        if "errors" in profile_data:
            raise HelsinkiProfileError(f"GraphQL error: {str(profile_data['errors'])}")

        national_identification_number = (
            profile_data.get("data", {})
            .get("myProfile", {})
            .get("verifiedPersonalInformation", {})
            .get("nationalIdentificationNumber")
        )

        return {"user_ssn": national_identification_number}

    def get_api_access_token(self, oidc_access_token):
        """
        Exchanges OIDC access token for a Helsinki Profile API access token using
        Tunnistus (Keycloak).
        """

        try:
            response = requests.post(
                app_settings.TUNNISTUS_API_TOKENS_ENDPOINT,
                data={
                    "audience": app_settings.HELSINKI_PROFILE_AUDIENCE,
                    "grant_type": "urn:ietf:params:oauth:grant-type:uma-ticket",
                    "permission": "#access",
                },
                headers={
                    "Authorization": f"Bearer {oidc_access_token}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

        except RequestException as e:
            raise HelsinkiProfileError(str(e))

        if app_settings.HELSINKI_PROFILE_SCOPE not in data:
            raise HelsinkiProfileError(
                "Could not obtain API access token, check setting"
                " HELSINKI_PROFILE_SCOPE"
            )
        return data[app_settings.HELSINKI_PROFILE_SCOPE]
