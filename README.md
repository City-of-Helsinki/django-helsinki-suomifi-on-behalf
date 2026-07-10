# django-helsinki-suomifi-on-behalf

Suomi.fi on-behalf (eAuthorizations / "Valtuudet") integration helpers for
City of Helsinki Django apps.

This library packages the Suomi.fi eAuthorizations (Valtuudet) on-behalf client
flow and the supporting utilities so they can be reused across services instead of
being copy-pasted.

## Installation

```bash
pip install django-helsinki-suomifi-on-behalf
```

The package depends on `django` and `requests`.

## What is included

| Module | Purpose |
| --- | --- |
| `suomifi_on_behalf.views` | eAuthorizations request/callback views |
| `suomifi_on_behalf.ssn` | Pluggable SSN (hetu) resolvers |
| `suomifi_on_behalf.client` | Checksum and Valtuudet / OIDC userinfo HTTP calls |
| `suomifi_on_behalf.sessions` | Session token storage and redirect helpers |
| `suomifi_on_behalf.signals` | `suomifi_mandate_queried` / `suomifi_mandate_query_failed` |
| `suomifi_on_behalf.helsinki_profile` | Helsinki Profile GraphQL client (SSN source) |
| `suomifi_on_behalf.app_settings` | Namespaced access to the library's settings |

The most commonly used names are re-exported from the package root, e.g.
`from suomifi_on_behalf import OidcUserinfoSsnResolver, SsnResolutionError`.

## National identification number (hetu) resolution

The eAuthorizations flow needs the user's national identification number to register
and query mandates. How the SSN is obtained is fully pluggable via the
`SUOMIFI_ON_BEHALF_SSN_RESOLVERS` setting, a list of resolvers tried in order until
one succeeds:

```python
SUOMIFI_ON_BEHALF_SSN_RESOLVERS = [
    "suomifi_on_behalf.ssn.OidcUserinfoSsnResolver",
    "suomifi_on_behalf.ssn.HelsinkiProfileSsnResolver",
]
```

Each entry is a dotted path to a callable `(request) -> str` (or to a class that is
instantiated with no arguments and is itself callable). A resolver returns the hetu
or raises `suomifi_on_behalf.ssn.SsnResolutionError`; when every resolver
raises, the request view redirects the user to `SUOMIFI_ON_BEHALF_LOGIN_ERROR_URL`.

Built-in resolvers:

1. **`OidcUserinfoSsnResolver`**: reads the `national_id_num` claim from
   `SUOMIFI_ON_BEHALF_OIDC_USERINFO_ENDPOINT`. Subclass and set `claim` to match your
   IdP. Only plain JSON userinfo is supported; a signed-JWT (`application/jwt`)
   userinfo response is rejected with a clear error, in which case supply a custom
   resolver that verifies and decodes it.
2. **`HelsinkiProfileSsnResolver`**: reads
   `verifiedPersonalInformation.nationalIdentificationNumber` from the Helsinki
   Profile GraphQL API.

A typical deployment configures the userinfo resolver, optionally with the Helsinki
Profile resolver as a fallback (as shown above). For any other identity provider,
provide your own callable:

```python
def my_ssn_resolver(request):
    ssn = request.session.get("my_ssn")
    if not ssn:
        from suomifi_on_behalf.ssn import SsnResolutionError
        raise SsnResolutionError("no SSN available")
    return ssn

SUOMIFI_ON_BEHALF_SSN_RESOLVERS = ["myapp.auth.my_ssn_resolver"]
```

## URL configuration

Wire the eAuthorizations views (they provide the `eauth_authentication_init` and
`eauth_authentication_callback` route names):

```python
urlpatterns = [
    path("", include("suomifi_on_behalf.urls")),
]
```

## Settings

### eAuthorizations (Valtuudet)

All of this library's own settings are prefixed `SUOMIFI_ON_BEHALF_`, have defaults,
and are read through `suomifi_on_behalf.app_settings`. Standard Django settings
(`LOGIN_REDIRECT_URL`, `LANGUAGE_COOKIE_NAME`) are used directly.

```python
SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_BASE_URL = "https://asiointivaltuustarkistus.suomi.fi"
SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_CLIENT_ID = "..."
SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_CLIENT_SECRET = "..."
SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_API_OAUTH_SECRET = "..."

# Where to send the user after a successful login (standard Django setting).
LOGIN_REDIRECT_URL = "https://frontend.example.test/success"
# Where to send the user when authorization fails.
SUOMIFI_ON_BEHALF_LOGIN_ERROR_URL = "https://frontend.example.test/failure"

# Used to validate dynamic redirect targets. REQUIRE_HTTPS defaults to
# request.is_secure() when unset.
SUOMIFI_ON_BEHALF_REDIRECT_ALLOWED_HOSTS = ["frontend.example.test"]
SUOMIFI_ON_BEHALF_REDIRECT_REQUIRE_HTTPS = True
```

### OIDC userinfo / Helsinki Profile

Used by `OidcUserinfoSsnResolver` and `HelsinkiProfileSsnResolver`:

```python
SUOMIFI_ON_BEHALF_OIDC_USERINFO_ENDPOINT = "https://tunnistus.example.test/openid/userinfo"

# Helsinki Profile
SUOMIFI_ON_BEHALF_HELSINKI_PROFILE_API_URL = "https://profile-api.example.test/graphql/"
SUOMIFI_ON_BEHALF_HELSINKI_PROFILE_AUDIENCE = "profile-api"
SUOMIFI_ON_BEHALF_HELSINKI_PROFILE_SCOPE = "https://api.hel.fi/auth/helsinkiprofile"
SUOMIFI_ON_BEHALF_TUNNISTUS_API_TOKENS_ENDPOINT = "https://tunnistus.example.test/api-tokens/"
```

## Signals

Connect to the mandate query signals for audit logging:

```python
from suomifi_on_behalf.signals import (
    suomifi_mandate_queried,
    suomifi_mandate_query_failed,
)
```

`suomifi_mandate_queried` is sent with `request`, `request_id` and
`organization_roles`; `suomifi_mandate_query_failed` is sent with `request`,
`request_id` and `error`.

## Development

```bash
hatch test      # run the test suite
hatch run lint      # run pre-commit hooks
```
