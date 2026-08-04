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
`INSTALLED_APPS`. Wire its URLs (see [Quickstart](#quickstart)) and connect any signals
from your own app.

## Quickstart

1. **Wire the URLs.** Include the library's URLconf; it provides the
   `eauth_authentication_init` and `eauth_authentication_callback` route names:

   ```python
   urlpatterns = [
       path("", include("suomifi_on_behalf.urls")),
   ]
   ```

   Register the callback URL with Suomi.fi as the redirect URI (it is always sent as
   `https://`).

2. **Set the required settings.** The minimum needed to run the flow:

   ```python
   # Issued during Suomi.fi Valtuudet onboarding.
   SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_BASE_URL = "https://asiointivaltuustarkistus.suomi.fi"
   SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_CLIENT_ID = "..."
   SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_CLIENT_SECRET = "..."
   SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_API_OAUTH_SECRET = "..."

   # At least one SSN resolver so the flow can obtain the user's hetu.
   SUOMIFI_ON_BEHALF_SSN_RESOLVERS = [
       "suomifi_on_behalf.ssn.OidcUserinfoSsnResolver",
   ]
   SUOMIFI_ON_BEHALF_OIDC_USERINFO_ENDPOINT = "https://tunnistus.example.test/openid/userinfo"

   # Where the user lands after success and after failure.
   SUOMIFI_ON_BEHALF_LOGIN_SUCCESS_URL = "https://frontend.example.test/success"
   SUOMIFI_ON_BEHALF_LOGIN_ERROR_URL = "https://frontend.example.test/failure"
   ```

   See the [Settings reference](#settings) for the full list, defaults, and optional
   knobs.

3. **Start the flow.** Send an already authenticated user (see [Concepts](#concepts))
   to the `eauth_authentication_init` route to begin.

For the end-to-end walkthrough, see [docs/eauth-flow.md](docs/eauth-flow.md).

## Concepts

**On-behalf / mandate model.** The flow authenticates a person and then asks Suomi.fi
Valtuudet which organization that person may act on behalf of. The result - the
"organization roles" or *mandate* - carries the acting company's business id, name, and
the Suomi.fi role codes the person holds. It is stored in
`request.session["organization_roles"]`.

**You bring your own login.** This library does **not** log the user in. It builds on an
existing OIDC login that your app provides (no OIDC or SAML backend ships here - use, for
example, `mozilla-django-oidc`). The flow reads one session key from that login,
`request.session["oidc_access_token"]`, which the built-in SSN resolvers use to obtain
the hetu. If it is missing when the init view runs, SSN resolution fails and the user is
redirected to the error page.

**Only one organization role is kept.** Only the **first** organization role from the
API response is stored. If a person holds mandates for several organizations, this
library keeps just one; there is no built-in "switch company" flow. The library confirms
the user holds *a* mandate for the selected company but does **not** filter by a specific
mandate/authorization type - inspect the `roles` list and enforce any specific mandate in
your own code.

### What is included

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

## Reference

### Settings

All of this library's own settings are prefixed `SUOMIFI_ON_BEHALF_`, have defaults, and
are read through `suomifi_on_behalf.app_settings`. The standard Django setting
`LANGUAGE_COOKIE_NAME` is used directly.

| Setting | Required by | Default | Purpose |
| --- | --- | --- | --- |
| `SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_BASE_URL` | core flow | `""` | Valtuudet API base URL. Use the Suomi.fi / DVV test base in non-production; the correct value comes from onboarding. |
| `SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_CLIENT_ID` | core flow | `""` | Client id issued at onboarding. |
| `SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_CLIENT_SECRET` | core flow | `""` | HMAC-SHA256 key that signs the checksum header on every Valtuudet API call. |
| `SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_API_OAUTH_SECRET` | core flow | `""` | HTTP Basic password for the OAuth token exchange (`/oauth/token`). |
| `SUOMIFI_ON_BEHALF_SSN_RESOLVERS` | core flow | `None` | Ordered list of dotted paths to SSN resolvers, tried until one succeeds. |
| `SUOMIFI_ON_BEHALF_LOGIN_SUCCESS_URL` | core flow | `""` | Where to send the user after a successful login. Required: the init view raises `ImproperlyConfigured` when it is unset. |
| `SUOMIFI_ON_BEHALF_LOGIN_ERROR_URL` | core flow | `""` | Where to send the user when authorization fails. |
| `SUOMIFI_ON_BEHALF_REDIRECT_ALLOWED_HOSTS` | dynamic next-url | `[]` | Extra hostnames allowed when the app stores an optional per-login destination in `request.session["eauth_next_url"]` (the request's own host is always allowed). See [Redirects](docs/eauth-flow.md#3-redirects). |
| `SUOMIFI_ON_BEHALF_REDIRECT_REQUIRE_HTTPS` | dynamic next-url | `None` (falls back to `request.is_secure()`) | Whether that `eauth_next_url` destination must be HTTPS. See [Redirects](docs/eauth-flow.md#3-redirects). |
| `SUOMIFI_ON_BEHALF_OIDC_USERINFO_ENDPOINT` | `OidcUserinfoSsnResolver` | `""` | OIDC userinfo endpoint read for the hetu claim. |
| `SUOMIFI_ON_BEHALF_OIDC_VERIFY_SSL` | `OidcUserinfoSsnResolver` | `True` | Verify TLS on the userinfo request. |
| `SUOMIFI_ON_BEHALF_OIDC_TIMEOUT` | `OidcUserinfoSsnResolver` | `None` | Userinfo request timeout in seconds. |
| `SUOMIFI_ON_BEHALF_OIDC_PROXY` | `OidcUserinfoSsnResolver` | `None` | Proxy configuration for the userinfo request. |
| `SUOMIFI_ON_BEHALF_HELSINKI_PROFILE_API_URL` | `HelsinkiProfileSsnResolver` | `""` | Helsinki Profile GraphQL URL. |
| `SUOMIFI_ON_BEHALF_HELSINKI_PROFILE_AUDIENCE` | `HelsinkiProfileSsnResolver` | `""` | API-token audience. |
| `SUOMIFI_ON_BEHALF_HELSINKI_PROFILE_SCOPE` | `HelsinkiProfileSsnResolver` | `""` | API-token scope. |
| `SUOMIFI_ON_BEHALF_TUNNISTUS_API_TOKENS_ENDPOINT` | `HelsinkiProfileSsnResolver` | `""` | Tunnistus/Keycloak API-tokens endpoint. |
| `SUOMIFI_ON_BEHALF_COMPANY_RESOLVERS` | company data | `None` | Ordered list of dotted paths to company resolvers, tried until one succeeds. |
| `SUOMIFI_ON_BEHALF_YTJ_BASE_URL` | `YtjCompanyResolver` | `""` | YTJ (avoindata PRH v3) base URL. |
| `SUOMIFI_ON_BEHALF_YTJ_TIMEOUT` | `YtjCompanyResolver` | `30` | YTJ request timeout in seconds. |
| `SUOMIFI_ON_BEHALF_CACHE_COMPANY_IN_SESSION` | company data | `True` | Whether `get_company` caches the resolved company in `request.session["company"]`. Set `False` when your app is the source of truth for company data and re-resolves each request; the session is then never read or written. |

`CLIENT_ID`, `CLIENT_SECRET` and `API_OAUTH_SECRET` are issued during Suomi.fi Valtuudet
onboarding. The checksum and token flows are described in the Suomi.fi documentation
(Finnish only): the checksum calculation in
[palveluhallinta artikkeli 5a781dc7](https://palveluhallinta.suomi.fi/fi/tuki/artikkelit/5a781dc75cb4f10dde9735e4)
and the overall Web API flow in
[palveluhallinta artikkeli 592d7745](https://palveluhallinta.suomi.fi/fi/tuki/artikkelit/592d774503f6d100018db5dd).

**Language segment in redirects.** When a `LANGUAGE_COOKIE_NAME` cookie is present, the
success and failure redirects get the language appended as a path segment: with
`SUOMIFI_ON_BEHALF_LOGIN_SUCCESS_URL = "https://frontend.example.test/success"` and a
`fi` cookie the user is sent to `https://frontend.example.test/success/fi/`. With no
language cookie the URL is used unchanged. Build your frontend routes to expect this.

### SSN (hetu) resolvers

The flow needs the user's national identification number to register and query mandates.
How it is obtained is pluggable via `SUOMIFI_ON_BEHALF_SSN_RESOLVERS`, a list of dotted
paths tried in order until one succeeds. Each entry is a callable `(request) -> str` (or
a class instantiated with no arguments and itself callable) that returns the hetu or
raises `suomifi_on_behalf.ssn.SsnResolutionError`; when every resolver raises, the
request view redirects to `SUOMIFI_ON_BEHALF_LOGIN_ERROR_URL`.

Built-in resolvers:

1. **`OidcUserinfoSsnResolver`** - reads the `national_id_num` claim from
   `SUOMIFI_ON_BEHALF_OIDC_USERINFO_ENDPOINT`. Subclass and set `claim` to match your
   IdP. Only plain JSON userinfo is supported; a signed-JWT (`application/jwt`) response
   is rejected with a clear error, in which case supply a custom resolver that verifies
   and decodes it.
2. **`HelsinkiProfileSsnResolver`** - reads
   `verifiedPersonalInformation.nationalIdentificationNumber` from the Helsinki Profile
   GraphQL API.

Writing a custom resolver and the full worked example live in
[docs/eauth-flow.md](docs/eauth-flow.md).

### Company data resolvers

Turning the mandate's business id into fuller company data is pluggable via
`SUOMIFI_ON_BEHALF_COMPANY_RESOLVERS`, tried in order until one succeeds. Each entry is a
callable `(request) -> dict` (or a no-arg class that is callable) that returns a company
dict or raises `suomifi_on_behalf.company.CompanyResolutionError`; when every resolver
raises, `get_company` re-raises `CompanyResolutionError`.

Built-in resolvers:

1. **`YtjCompanyResolver`** - looks the company up in the YTJ (avoindata PRH v3) open
   data API by business id and returns the preferred (Finnish, then Swedish) name,
   company form, industry and address. Requires `SUOMIFI_ON_BEHALF_YTJ_BASE_URL`.
2. **`OrganizationRolesCompanyResolver`** - performs no external call and returns only
   the `name` and `business_id` carried by the mandate. Intended as the terminal
   fallback in a chain.

The built-in resolvers return the keys documented above, but `get_company` does not
validate or enforce a schema: it passes through whatever dict the configured resolver
returns. A custom resolver may therefore return any JSON-serializable dict, including a
**superset** of the built-in keys (for example an integer `company_form_code` or a
`industry_code` string that your own model persists). The effective contract is "whatever
your configured resolver returns," so when chaining resolvers, have them agree on a
superset of keys to give callers a stable shape.

The full worked example (persisting to your own model, a DRF view, a custom resolver,
audit signals and tests) lives in [docs/company-data.md](docs/company-data.md).

### Public API

`get_organization_roles(request)` returns the cached mandate or performs the HTTP query
on a miss:

```python
from suomifi_on_behalf import get_organization_roles

roles = get_organization_roles(request)
# {"identifier": "0877830-0", "name": "Example Oy", "complete": True, "roles": ["NIMKO"]}
```

`identifier` is the company's business id, `name` its name, and `roles` a list of
Suomi.fi mandate/role codes (for example `NIMKO`) the person holds for that company.

`get_company(request)` returns the cached `company` dict from the session when present,
otherwise resolves it once from the mandate already in the session, caches it in
`request.session["company"]`, and emits `suomifi_company_resolved`:

```python
from suomifi_on_behalf import get_company

company = get_company(request)
# {"name": ..., "business_id": ..., "company_form": ..., "industry": ...,
#  "street_address": ..., "postcode": ..., "city": ...}
```

Pass `get_company(request, use_cache=False)` to skip the session entirely - the resolver
runs and nothing is read from or written to `request.session["company"]`. Omitting the
argument follows the `SUOMIFI_ON_BEHALF_CACHE_COMPANY_IN_SESSION` setting (default
`True`); an explicit `use_cache` overrides it. Disable caching when your application is
the source of truth for company data and re-resolves on each request. The
`suomifi_company_resolved` / `suomifi_company_resolution_failed` signals fire whenever the
resolver runs regardless of caching; a cache hit emits nothing.

This library only returns the data. Persisting a `Company` record (and its schema) is
left entirely to the consuming application.

Both helpers let `requests` exceptions (`RequestException` / `HTTPError`) propagate and
do **not** redirect on failure. The redirect-to-error behavior lives only in the callback
view, so wrap these calls accordingly when using them from your own views.

### Signals

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

Connect receivers to these `suomifi_on_behalf.signals` objects specifically. They are
distinct `Signal` instances, not the same objects as any similarly named signals that
may already exist in your project (for example if you migrated incrementally from a
copy-pasted version of this code). Connecting a receiver to a different signal object
silently receives nothing.

### Session keys and logout

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
