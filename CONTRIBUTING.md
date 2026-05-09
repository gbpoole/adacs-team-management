# Contributing

## Development setup

### Prerequisites

- Python 3.14+
- [Poetry](https://python-poetry.org/docs/#installation)
- Node.js (version managed via `.nvmrc` — use [nvm](https://github.com/nvm-sh/nvm))
- Docker and Docker Compose (for running the full stack locally)

### Install dependencies

```bash
poetry install --with dev
nvm use
npm install
```

### Configure environment

```bash
cp .env.template .env
# Edit .env — set DJANGO_SECRET_KEY, database credentials, etc.
```

For local development without Docker you can use SQLite (the test settings use it automatically). The `.env` MySQL credentials are only needed when running the Docker stack.

---

## Running the app locally

### Without Docker (Django dev server)

```bash
cd src && DJANGO_SETTINGS_MODULE=config.settings.development poetry run python manage.py migrate
cd src && DJANGO_SETTINGS_MODULE=config.settings.development poetry run python manage.py runserver
```

CSS is compiled separately by Tailwind. Run in watch mode alongside the dev server:

```bash
npm run dev
```

### With Docker

Build and start all containers:

```bash
docker compose build django nginx
docker compose up -d
```

Static files (JS, CSS) are baked into the `nginx` image at build time. After any JS or CSS change, rebuild both:

```bash
docker compose build django nginx && docker compose up -d django nginx
```

After Python, template, or migration-only changes, only the `django` image needs rebuilding:

```bash
docker compose build django && docker compose up -d django
```

---

## Seed data

A `seed_test_data` management command populates the database with realistic-looking fixture data for development and manual testing.

### Running locally

```bash
cd src && DJANGO_SETTINGS_MODULE=config.settings.development poetry run python manage.py seed_test_data --clear
```

### Running in Docker

Use the `docker_dev` settings module, which extends production settings but explicitly enables seeding:

```bash
docker compose exec django poetry run python manage.py seed_test_data --clear --settings=config.settings.docker_dev
```

### Production guard

**`seed_test_data` cannot run in production.** The command checks for `SEED_DATA_ALLOWED = True` in the active settings module before doing anything. This flag is set only in `development.py`, `test.py`, and `docker_dev.py`. The production settings module (`prod.py`) does not set it, so any attempt to run `seed_test_data` against production settings raises a `CommandError` and exits immediately.

---

## Tests

```bash
cd src && DJANGO_SETTINGS_MODULE=config.settings.test poetry run python manage.py test apps.planning tests
```

Run a single test class or method:

```bash
cd src && DJANGO_SETTINGS_MODULE=config.settings.test poetry run python manage.py test apps.planning.tests.test_views.PlanningViewTest
```

Tests use SQLite (no MySQL required). Fixtures are built with `factory-boy`; factories live in `src/apps/planning/tests/factories.py`.

### Checking for missing migrations

```bash
cd src && DJANGO_SETTINGS_MODULE=config.settings.test poetry run python manage.py makemigrations --check --dry-run
```

---

## Linting and formatting

### Python (ruff)

```bash
poetry run ruff check src/apps/          # lint
poetry run ruff format --check src/apps/ # format check
poetry run ruff format src/apps/         # auto-format
```

### HTML templates (djlint)

```bash
poetry run djlint src/apps/templates/ --check    # check
poetry run djlint src/apps/templates/ --reformat # auto-format
```

**Important:** djlint's JS formatter (`format_js = true`) will corrupt Django template tags inside `<script>` blocks (e.g. `{{ var|filter }}`). Any `<script>` block containing Django template expressions must be wrapped with:

```html
{# djlint:off #}
<script>
  window.myConfig = { value: {{ my_var|default:"null" }} };
</script>
{# djlint:on #}
```

---

## Migrations

```bash
cd src && DJANGO_SETTINGS_MODULE=config.settings.development poetry run python manage.py makemigrations
cd src && DJANGO_SETTINGS_MODULE=config.settings.development poetry run python manage.py migrate
```

After creating a migration, run the test suite and check that `--check --dry-run` shows no outstanding migrations.

---

## CSS build

Tailwind CSS is compiled from `styles.css`:

```bash
npm run build   # production (minified)
npm run dev     # watch mode for development
```

The compiled CSS is an input to the Docker build — run `npm run build` before committing if you change `styles.css` or add new Tailwind classes.

---

## Architecture overview

- **Backend:** Django 5.2, MySQL (SQLite for tests), Django REST Framework, django-allauth
- **Frontend:** Tailwind CSS v4 + daisyUI v5, HTMX, no JS framework
- **Auth:** Email-only login via django-allauth with mandatory email verification and reCAPTCHA
- **App layout:**
  - `src/apps/users/` — custom `User` model (email-based, `pm`/`user` roles)
  - `src/apps/planning/` — all domain logic, models, views, templates, tests
  - `src/config/` — settings, URL conf, API router

The domain model centres on `Semester`, `Project`, `DeveloperProfile`, `Phase`, and `DeveloperLane`. Access control is managed through `UserProjectAccess` records (global, not per-semester) rather than per-semester observer tables.

See `CLAUDE.md` for a full architecture reference used by AI assistants working in this repo.

---

## CI / CD

GitHub Actions runs on every push and pull request to `main`:

| Job | What it checks |
|---|---|
| `lint` | ruff lint, ruff format, djlint template formatting |
| `test` | Migration completeness, full Django test suite |
| `docker` | Docker image builds without error |

All three jobs must pass before a PR can be merged. Branch protection on `main` also requires at least one approving review and that branches be up to date before merging.

Dependabot raises weekly PRs to keep Python and GitHub Actions dependencies current.

---

## Making a change

1. Create a branch from `main`
2. Make your changes; run tests and linters locally before pushing
3. Open a PR against `main` — CI runs automatically
4. Get at least one review approval
5. Merge once all checks pass