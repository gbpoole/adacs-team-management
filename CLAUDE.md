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

## Architecture

### Stack
- **Backend:** Django 5.2, MySQL (SQLite for tests), Django REST Framework, django-allauth
- **Frontend:** Tailwind CSS v4 + daisyUI v5, HTMX (no JS framework), crispy-forms with `crispywind` pack
- **Auth:** django-allauth with email-only login (no username), mandatory email verification

### App structure
- `src/apps/users/` — custom `User` model (email-based, no username) with `Role` choices: `admin`, `pm`, `developer`, `observer`
- `src/apps/planning/` — all domain logic, models, views, templates, tests
- `src/config/` — settings (base/development/test/prod), URL conf, API router

### Domain model (`src/apps/planning/models.py`)
- **`DeveloperProfile`** / **`ObserverProfile`** — extend `User` via OneToOne; observers have M2M `project_access`
- **`Semester`** — year + type (A=Jan-Jun, B=Jul-Dec); `Semester.get_current()` auto-creates if missing
- **`Project`** — has a `Stream`, colour, tags, and per-semester names via `ProjectSemesterName`; `project.name_for_semester(semester)` resolves the display name with fallback
- **`ProjectAllocation`** — weeks (new + carryover) per project per semester
- **`SemesterDeveloper`** — effort available (weeks) per developer per semester
- **`Leave`** — date ranges for a developer; affects `Phase.effort_weeks()` calculation
- **`Phase`** — a developer working on a project for a date range within a semester; `effort_weeks()` counts working days minus leave, divided by 5, times `effort_multiplier`
- **`Tag`** — shared across developers and projects for filtering

### Views & URL structure (`/planning/`)
Access control uses `RoleRequiredMixin` with per-view `allowed_roles`. URL namespace is `planning`.

| URL | View | Roles |
|-----|------|-------|
| `/planning/developers/` | `DevelopersView` | admin, pm, developer |
| `/planning/observers/` | `ObserversView` | admin, pm |
| `/planning/projects/` | `ProjectsView` | all roles |
| `/planning/leave/` | `LeaveView` | admin, pm, developer |
| `/planning/planning/` | `PlanningView` | admin, pm |
| `/planning/schedule/` | `ScheduleView` | admin, pm |

The Planning and Schedule pages render week-by-week Gantt-style timelines. The shared helpers `_week_starts`, `_coverage`, and `_build_timeline_layers` in `views.py` build the grid data passed to templates. Phases are placed into non-overlapping layers; leave periods fill gaps between phases.

### Templates
All templates live in `src/apps/templates/`. Planning-specific templates are under `planning/`. The base layout is `base.html`.

### Tests
Tests use `factory_boy` factories in `src/apps/planning/tests/factories.py`. The test settings use SQLite. Test classes are in `test_models.py` and `test_views.py` under `src/apps/planning/tests/`.
