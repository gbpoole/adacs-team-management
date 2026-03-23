#!/bin/sh
DJANGO_SETTINGS_MODULE=config.settings.prod poetry run python manage.py migrate
poetry run gunicorn config.wsgi --bind 0.0.0.0:8000 --workers 8 --timeout 60
