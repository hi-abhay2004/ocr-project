from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import SECRET_KEY, env

DEBUG = False

# base.py falls back to a hardcoded placeholder when DJANGO_SECRET_KEY isn't
# set, so dev/test work with zero config — but that placeholder is sitting
# in the public repo. If it ever reached production unnoticed, anyone could
# forge a valid session/CSRF token and, since SIMPLE_JWT never overrides
# SIGNING_KEY (it defaults to SECRET_KEY), a valid access/refresh JWT for
# any user — a full auth bypass needing no password. Prod is the one
# environment where "missing env var" must fail loudly at startup, not
# silently run on a key every attacker already has.
_INSECURE_DEFAULT_SECRET_KEY = "dev-only-insecure-key-change-me"
if not SECRET_KEY or SECRET_KEY == _INSECURE_DEFAULT_SECRET_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY is not set (or is still the development default) — "
        "set a real, random secret in the production environment before starting."
    )

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
