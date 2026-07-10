from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "secret"
DEBUG = True

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "tests",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "tests.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

USE_TZ = True
STATIC_URL = "static/"
LANGUAGE_CODE = "en"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

# Suomi.fi eAuthorizations (Valtuudet) settings. Most are overridden per-test.
SUOMIFI_ON_BEHALF_SSN_RESOLVERS = [
    "suomifi_on_behalf.ssn.OidcUserinfoSsnResolver",
    "suomifi_on_behalf.ssn.HelsinkiProfileSsnResolver",
]
SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_BASE_URL = "http://example.test"
SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_CLIENT_ID = "test"
SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_CLIENT_SECRET = "test"
SUOMIFI_ON_BEHALF_EAUTHORIZATIONS_API_OAUTH_SECRET = "test"

LOGIN_REDIRECT_URL = "http://example.test/success"
SUOMIFI_ON_BEHALF_LOGIN_ERROR_URL = "http://example.test/failure"

SUOMIFI_ON_BEHALF_OIDC_USERINFO_ENDPOINT = "http://example.test/userinfo"
SUOMIFI_ON_BEHALF_REDIRECT_ALLOWED_HOSTS = ["example.test"]
SUOMIFI_ON_BEHALF_REDIRECT_REQUIRE_HTTPS = False
