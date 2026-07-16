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

The package depends on `django` and `requests`, and supports Python 3.10 and later
with Django 5.2 and 6.0.

There is no app config to register: `suomifi_on_behalf` does not need to be added to
`INSTALLED_APPS`. Wire its URLs (see below) and connect any signals from your own app.

## What is included

| Module | Purpose |
| --- | --- |
| `suomifi_on_behalf.views` | eAuthorizations request/callback views |
| `suomifi_on_behalf.ssn` | Pluggable SSN (hetu) resolvers |
| `suomifi_on_behalf.company` | Pluggable company data resolvers |
| `suomifi_on_behalf.client` | Checksum and Valtuudet / OIDC userinfo HTTP calls |
| `suomifi_on_behalf.sessions` | Session token storage and redirect helpers |
| `suomifi_on_behalf.signals` | `suomifi_mandate_queried` / `suomifi_mandate_query_failed` |
| `suomifi_on_behalf.helsinki_profile` | Helsinki Profile GraphQL client (SSN source) |
| `suomifi_on_behalf.app_settings` | Namespaced access to the library's settings |

The most commonly used names are re-exported from the package root, e.g.
`from suomifi_on_behalf import OidcUserinfoSsnResolver, SsnResolutionError`.

## Guides

- [docs/eauth-flow.md](docs/eauth-flow.md) - wiring the eAuthorizations flow and SSN
  resolution end to end (start here).
- [docs/company-data.md](docs/company-data.md) - fetching and persisting company data.

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

## Organization roles (the mandate)

After the callback completes, the library queries Suomi.fi Valtuudet and stores the
user's mandate in `request.session["organization_roles"]`. Read it with
`get_organization_roles(request)`:

```python
from suomifi_on_behalf import get_organization_roles

roles = get_organization_roles(request)
# {"identifier": "0877830-0", "name": "Example Oy", "complete": True, "roles": ["NIMKO"]}
```

- `identifier` is the company's business id, `name` its name, and `roles` a list of
  Suomi.fi mandate/role codes (for example `NIMKO`) that the person holds for that
  company.
- Only the **first** organization role from the API response is stored. If a person
  holds mandates for several organizations, this library keeps just one; there is no
  built-in "switch company" flow.
- The library confirms the user holds *a* mandate for the selected company but does
  **not** filter by a specific mandate/authorization type. If you need to gate on a
  particular mandate, inspect `roles` and enforce that in your own code.

`get_organization_roles` returns the cached roles or performs the HTTP query on a miss,
letting `requests` exceptions (`RequestException` / `HTTPError`) propagate; it does
**not** redirect on failure. The redirect-to-error behavior lives only in the callback
view, so wrap the call accordingly when you use it from your own views (the same applies
to `get_company`).

## Company data resolution

After a successful eAuthorizations login the mandate ("organization roles") stored in
the session carries the acting company's business id (`identifier`) and name. Turning
that into fuller company data is pluggable via the
`SUOMIFI_ON_BEHALF_COMPANY_RESOLVERS` setting, a list of resolvers tried in order until
one succeeds:

```python
SUOMIFI_ON_BEHALF_COMPANY_RESOLVERS = [
    "suomifi_on_behalf.company.YtjCompanyResolver",
    "suomifi_on_behalf.company.OrganizationRolesCompanyResolver",
]
```

Each entry is a dotted path to a callable `(request) -> dict` (or to a class that is
instantiated with no arguments and is itself callable). A resolver returns a company
dict or raises `suomifi_on_behalf.company.CompanyResolutionError`; when every resolver
raises, `get_company` re-raises `CompanyResolutionError`.

Built-in resolvers:

1. **`YtjCompanyResolver`**: looks the company up in the YTJ (avoindata PRH v3) open
   data API by business id and returns the preferred (Finnish, then Swedish) name,
   company form, industry and address. Requires `SUOMIFI_ON_BEHALF_YTJ_BASE_URL`.
2. **`OrganizationRolesCompanyResolver`**: performs no external call and returns only
   the `name` and `business_id` carried by the mandate. Intended as the terminal
   fallback in a chain.

Use `get_company(request)` to run the configured chain. It returns the cached `company`
dict from the session when present, otherwise resolves it once from the mandate already
in the session, caches it in `request.session["company"]`, and emits
`suomifi_company_resolved`:

```python
from suomifi_on_behalf import get_company

company = get_company(request)
# {"name": ..., "business_id": ..., "company_form": ..., "industry": ...,
#  "street_address": ..., "postcode": ..., "city": ...}
```

This library only returns the data. Persisting a `Company` record (and its schema) is
left entirely to the consuming application.

For a full worked example (persisting to your own model, a DRF view, a custom resolver,
audit signals and tests), see [docs/company-data.md](docs/company-data.md).

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
# Production endpoint. In non-production, point this at the Suomi.fi / DVV test
# environment instead; the correct test base URL comes from your Valtuudet onboarding.
SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_BASE_URL = "https://asiointivaltuustarkistus.suomi.fi"
SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_CLIENT_ID = "..."
# HMAC-SHA256 key used to sign the checksum header on every Valtuudet API call.
SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_CLIENT_SECRET = "..."
# HTTP Basic password used for the OAuth token exchange (/oauth/token).
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

`CLIENT_ID`, `CLIENT_SECRET` and `API_OAUTH_SECRET` are issued during Suomi.fi Valtuudet
onboarding. The checksum and token flows are described in the Suomi.fi documentation
(Finnish only): the checksum calculation in
[palveluhallinta artikkeli 5a781dc7](https://palveluhallinta.suomi.fi/fi/tuki/artikkelit/5a781dc75cb4f10dde9735e4)
and the overall Web API flow in
[palveluhallinta artikkeli 592d7745](https://palveluhallinta.suomi.fi/fi/tuki/artikkelit/592d774503f6d100018db5dd).

**Language segment in redirects.** When a `LANGUAGE_COOKIE_NAME` cookie is present, the
successful-login redirect gets the language appended as a path segment: with
`LOGIN_REDIRECT_URL = "https://frontend.example.test/success"` and a `fi` cookie the
user is sent to `https://frontend.example.test/success/fi/`. With no language cookie the
URL is used unchanged. The failure redirect likewise inserts the language into the error
URL path. Build your frontend routes to expect this.

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

### Company data (YTJ)

Used by `YtjCompanyResolver`:

```python
SUOMIFI_ON_BEHALF_COMPANY_RESOLVERS = [
    "suomifi_on_behalf.company.YtjCompanyResolver",
    "suomifi_on_behalf.company.OrganizationRolesCompanyResolver",
]
SUOMIFI_ON_BEHALF_YTJ_BASE_URL = "https://avoindata.prh.fi/opendata-ytj-api/v3"
SUOMIFI_ON_BEHALF_YTJ_TIMEOUT = 30  # seconds (default)
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

The company resolution signals are:

```python
from suomifi_on_behalf.signals import (
    suomifi_company_resolved,
    suomifi_company_resolution_failed,
)
```

`suomifi_company_resolved` is sent with `request` and `company`;
`suomifi_company_resolution_failed` is sent with `request` and `error`.

## Sessions and logout

The flow stores several values in the Django session: `eauth_id_token`,
`eauth_access_token` (plus refresh/expiry variants), `organization_roles`, and the
cached `company`. The library provides no teardown helper, so clear them yourself on
logout:

```python
for key in (
    "eauth_id_token",
    "eauth_access_token",
    "eauth_access_token_expires",
    "eauth_refresh_token",
    "eauth_refresh_token_expires",
    "organization_roles",
    "company",
):
    request.session.pop(key, None)
```

Because these values include access tokens and personal mandate data, avoid the
signed-cookie session backend: it exposes the tokens to the client and can exceed the
cookie size limit. Use a server-side session backend (database, cache, or file).

## Development

```bash
hatch test      # run the test suite
hatch run lint      # run pre-commit hooks
```
