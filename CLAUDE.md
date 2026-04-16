# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ADACS Team Resource Allocation Tool — a Django 5.2 web app for allocating developers across projects on a semesterly basis. The full requirements spec is in `project_planning_spec_v1pt0.docx` at the repo root.

## Commands

All Django commands run from `src/` with the appropriate settings module.

**Run the dev server:**
```bash
cd src && DJANGO_SETTINGS_MODULE=config.settings.development poetry run python manage.py runserver
```

**Run all tests:**
```bash
cd src && DJANGO_SETTINGS_MODULE=config.settings.test poetry run python manage.py test apps.planning tests
```

**Run a single test module or class:**
```bash
cd src && DJANGO_SETTINGS_MODULE=config.settings.test poetry run python manage.py test apps.planning.tests.test_views.PlanningViewTest
```

**Lint:**
```bash
poetry run ruff check src/apps/
```

**Seed the database:**
```bash
cd src && DJANGO_SETTINGS_MODULE=config.settings.test poetry run python manage.py seed_test_data
```

**Build CSS (Tailwind):**
```bash
npm run build        # production, minified
npm run dev          # watch mode for development
```

**Migrations:**
```bash
cd src && DJANGO_SETTINGS_MODULE=config.settings.development poetry run python manage.py makemigrations
cd src && DJANGO_SETTINGS_MODULE=config.settings.development poetry run python manage.py migrate
```

**Docker — running manage.py inside the container:**
The virtualenv is at `/app/.venv/` inside the container; plain `python` won't find Django. Always use `poetry run`:
```bash
docker compose exec django poetry run python manage.py migrate
docker compose exec django poetry run python manage.py seed_test_data
```

**Docker — picking up source code changes:**
Source code is baked into the image at build time (`COPY src /app/src`). There is no live volume mount. After any code change, rebuild before testing in Docker:
```bash
docker compose build django && docker compose up -d django
```

## Architecture

### Stack
- **Backend:** Django 5.2, MySQL (SQLite for tests), Django REST Framework, django-allauth
- **Frontend:** Tailwind CSS v4 + daisyUI v5, HTMX (no JS framework), crispy-forms with `crispywind` pack
- **Auth:** django-allauth with email-only login (no username), mandatory email verification

### App structure
- `src/apps/users/` — custom `User` model (email-based, no username) with `Role` choices: `pm`, `user` (default). Developer/observer access is determined by `SemesterDeveloper`/`SemesterObserver` records, not by the role field.
- `src/apps/planning/` — all domain logic, models, views, templates, tests
- `src/config/` — settings (base/development/test/prod), URL conf, API router

### Domain model (`src/apps/planning/models.py`)
- **`DeveloperProfile`** — extends `User` via OneToOne; holds colour, base_effort_weeks, and base tags
- **`Semester`** — year + type (A=Jan-Jun, B=Jul-Dec); `Semester.get_current()` auto-creates if missing
- **`Project`** — belongs to `Stream`(s), has colour, tags, and per-semester names via `ProjectSemesterName`; `project.name_for_semester(semester)` resolves the display name with fallback
- **`ProjectAllocation`** — weeks (new + carryover) per project per semester
- **`SemesterDeveloper`** — effort available (weeks) per developer per semester; mutually exclusive with `SemesterObserver` for the same user+semester
- **`SemesterObserver`** — per-semester observer access record; grants a user view access to specific projects and/or streams; mutually exclusive with `SemesterDeveloper`
- **`Leave`** — date ranges for a developer; affects `Phase.effort_weeks()` calculation
- **`Phase`** — a developer working on a project for a date range within a semester; `effort_weeks()` counts working days minus leave, divided by 5, times `effort_multiplier`
- **`DeveloperLane`** — a visual row on the Gantt for one developer in one semester; a developer can have multiple lanes when phases overlap
- **`Tag`** — shared across developers and projects for filtering

### Access control
Three mixins in `views/_mixins.py` gate access based on role + semester participation:
- `RoleRequiredMixin` — restricts to `allowed_roles`; all write views use `allowed_roles = (Role.PM,)`
- `PMOrDeveloperMixin` — PM always allowed; others only if they have a `SemesterDeveloper` record with `effort_available > 0`
- `PMOrObserverMixin` — PM always allowed; others only if they have a `SemesterObserver` record
- `PMOrParticipantMixin` — PM always allowed; others if they are either a semester developer or observer

### Views & URL structure (`/planning/`)
URL namespace is `planning`.

| URL | View | Access |
|-----|------|--------|
| `/planning/developers/` | `DevelopersView` | PM or semester developer |
| `/planning/observers/` | `ObserversView` | PM only |
| `/planning/projects/` | `ProjectsView` | PM or semester participant |
| `/planning/leave/` | `LeaveView` | PM or semester developer |
| `/planning/planning/` | `PlanningView` | PM only |
| `/planning/schedule/` | `ScheduleView` | PM only |

The Planning and Schedule pages render week-by-week Gantt-style timelines. The shared helpers `_week_starts`, `_coverage`, and `_build_timeline_layers` in `views.py` build the grid data passed to templates. Phases are placed into non-overlapping layers; leave periods fill gaps between phases.

### Templates
All templates live in `src/apps/templates/`. Planning-specific templates are under `planning/`. The base layout is `base.html`.

### Tests
Tests use `factory_boy` factories in `src/apps/planning/tests/factories.py`. The test settings use SQLite. Test classes are in `test_models.py` and `test_views.py` under `src/apps/planning/tests/`.
