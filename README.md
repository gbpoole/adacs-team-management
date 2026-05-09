# ADACS Team Planning

A Django web application for allocating developers across projects on a semesterly basis. It provides Gantt-style planning and schedule views, project and leave management, and role-based access control for team members, observers, and project managers.

## Requirements

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose

That's it for production deployment. For local development without Docker, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Deployment

### 1. Configure environment

Copy the template and fill in your values:

```bash
cp .env.template .env
```

Required settings to change before first run:

| Variable | Description |
|---|---|
| `DJANGO_SECRET_KEY` | Random 50-character string — generate with the command below |
| `MYSQL_ROOT_PASSWORD` | Strong root password for MySQL |
| `MYSQL_PASSWORD` | Password for the application database user |
| `DOMAIN_NAME` | Your domain (e.g. `planning.example.org`) |
| `RECAPTCHA_PUBLIC_KEY` | Google reCAPTCHA v2 site key |
| `RECAPTCHA_PRIVATE_KEY` | Google reCAPTCHA v2 secret key |

Generate a secret key:
```bash
python3 -c 'from django.utils.crypto import get_random_string; print(get_random_string(50))'
```

### 2. Build and start

```bash
docker compose build django nginx
docker compose up -d
```

This starts:
- **django** — Gunicorn app server (auto-runs migrations on startup)
- **nginx** — Reverse proxy serving static files
- **db** — MySQL 8.4
- **mailpit** — Local mail catcher bound to `127.0.0.1:8025` (UI at `http://localhost:8025`); intercepts all outgoing email including password resets — do not expose this port publicly
- **cron** — Background job for queued email delivery

**Security note:** The Docker image itself contains no secrets. All credentials from `.env` are injected at container startup via `env_file` and are never baked into the image layers. Do not push the `.env` file into any repository or image registry.

### 3. Create a superuser

```bash
docker compose exec django poetry run python manage.py createsuperuser
```

All superusers are automatically given the PM role, giving full access to all planning features.

### 4. Access the app

Navigate to `http://localhost:8000` (or your configured domain). Log in with the superuser credentials you just created.

## Upgrading

After pulling new code:

```bash
# If only Python/template changes:
docker compose build django && docker compose up -d django

# If JS or CSS changed (nginx serves static files):
docker compose build django nginx && docker compose up -d django nginx
```

Migrations run automatically on container startup.

## Email

Outbound email (account verification, password reset) uses `django-post-office` with a background queue. In production, point `EMAIL_HOST` and `EMAIL_PORT` in `.env` at your SMTP server. The bundled `mailpit` service is for development only.
