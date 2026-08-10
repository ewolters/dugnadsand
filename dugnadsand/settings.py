"""Django settings for dugnadsand."""

from pathlib import Path

from .config import get_settings

BASE_DIR = Path(__file__).resolve().parent.parent
config = get_settings()

SECRET_KEY = config.secret_key
DEBUG = config.debug
ALLOWED_HOSTS = config.get_allowed_hosts()

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "site_app",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # Request observability: correlation IDs, exception capture, slow requests.
    "kjerne_platform.middleware.OpsMiddleware",
    "kjerne_platform.middleware.AnalyticsMiddleware",
    # Canonical host/scheme for search engines.
    "kjerne_platform.seo.CanonicalMiddleware",
    # Records colour drift in rendered HTML against this site's brand.json —
    # create-site writes one, so a new site is branded from birth. Reads the
    # response and never touches it; sampled, and fail-open throughout.
    "kjerne_platform.brand.middleware.BrandMiddleware",
    "kjerne_platform.varta.middleware.VartaMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Binds the connection to one organization. Fails closed: no tenant, no rows.
    "site_app.tenancy.TenantMiddleware",
    # Second factor first: someone who has proved only a password should be
    # sent to prove the second one, not to change a credential.
    "site_app.middleware.RequireMFAMiddleware",
    # After TenantMiddleware: reading request.user.member needs a bound tenant.
    "site_app.middleware.ForcePasswordChangeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "dugnadsand.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Unread badge on every page. Site-scoped on purpose — the
                # shared kjerne_platform.notify.notifications counts across
                # the whole federation, which would show a member another
                # product's notices here. Fails open.
                "site_app.notifications.badge",
                # The header shows a member's mark and name, so every app page
                # needs it — not just the views that remembered to pass it.
                "site_app.context.member",
            ],
        },
    },
]

WSGI_APPLICATION = "dugnadsand.wsgi.application"

# Database — PostgreSQL is required. No sqlite fallback: a missing DATABASE_URL
# must fail loudly, never silently run on an unbacked-up sqlite file.
from django.core.exceptions import ImproperlyConfigured

if not config.database_url:
    raise ImproperlyConfigured(
        "DUGNADSAND_DATABASE_URL is not set. This site must use PostgreSQL "
        "(provisioned by ctrl/add-db); sqlite is not permitted in production."
    )

import dj_database_url

DATABASES = {"default": dj_database_url.parse(config.database_url)}
DATABASES["default"]["CONN_MAX_AGE"] = 60

if "postgresql" not in DATABASES["default"].get("ENGINE", ""):
    raise ImproperlyConfigured(
        "DUGNADSAND_DATABASE_URL must be a postgresql:// URL "
        f"(got engine {DATABASES['default'].get('ENGINE')!r}); sqlite is not permitted."
    )

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Security — Cloudflare terminates TLS
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = False  # Cloudflare handles HTTPS redirect
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1")]

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "app.log",
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
        "varta": {
            "class": "logging.handlers.WatchedFileHandler",
            "filename": "/var/log/svend/varta.log",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "WARNING",
            "propagate": False,
        },
        "kjerne_platform.varta": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "kjerne_platform.varta.actions": {
            "handlers": ["varta"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}


# Password hashing — Argon2 primary (memory-hard), matching kjerne-services.
# PBKDF2 kept behind it so existing hashes still verify and upgrade on use.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]
