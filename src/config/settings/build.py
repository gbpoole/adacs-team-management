"""
Minimal settings for Docker build-time tasks (collectstatic only).

No credentials are required — secrets are injected at runtime via docker-compose
env_file and are never baked into the image. Never use this module to run the
application.
"""

from .base import *  # noqa: F403

# Placeholder — satisfies Django's import; never used at runtime.
SECRET_KEY = "build-time-placeholder-not-for-runtime-use"

ALLOWED_HOSTS = ["*"]

# collectstatic does not touch the database.
DATABASES = {}

# Use ManifestStaticFilesStorage for content-hashed filenames, same as production.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
    },
}
