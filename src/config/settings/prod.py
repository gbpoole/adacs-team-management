"""
Production settings (basically the same as base.py, which reads from the .env file)

However, we ensure that some settings (read from the environment) which are optional
in test and dev are required
"""

from .base import *  # noqa: F403
from decouple import config

DEBUG = False

# Fail if no SECRET_KEY is provided
config("DJANGO_SECRET_KEY")


# Fail if no database credentials are provided
config("MYSQL_DATABASE")
config("MYSQL_USER")
config("MYSQL_PASSWORD")
config("DJANGO_MYSQL_HOST")
config("DJANGO_MYSQL_PORT")


# Fail if no reCAPTCHA credentials are provided
RECAPTCHA_PUBLIC_KEY = config("RECAPTCHA_PUBLIC_KEY")
RECAPTCHA_PRIVATE_KEY = config("RECAPTCHA_PRIVATE_KEY")
USE_RECAPTCHA = True


# Use a better staticfiles storage engine
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
    },
}

ALLOWED_HOSTS = ["test-project.org"]

# Use the correct host when building in docker
DATABASES["default"]["HOST"] = "db"
