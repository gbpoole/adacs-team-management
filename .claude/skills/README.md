# Project Skills

These project-scoped Claude Code skills are available as slash commands. Type `/` in the Claude Code prompt to see them in autocomplete.

## Docker

| Skill | Description |
|-------|-------------|
| `/docker-up` | Start all Docker Compose services (Django, MySQL, nginx, mailpit, cron) |
| `/docker-down` | Stop all Docker Compose services |
| `/docker-rebuild` | Rebuild the Django image and restart the container (required after any code change) |
| `/docker-seed` | Rebuild + restart + seed the database with test data |
| `/docker-migrate` | Run Django database migrations inside the container |
| `/docker-logs` | Tail the Django container logs |

> **Note:** Source code is baked into the image at build time — always use `/docker-rebuild` after code changes before testing in Docker.

## Local Development

| Skill | Description |
|-------|-------------|
| `/run-tests [path]` | Run the Django test suite; optional argument narrows to a specific module or class (e.g. `apps.planning.tests.test_views.PlanningViewTest`) |
| `/lint` | Run `ruff` over `src/apps/` |
| `/build-css [dev]` | Build Tailwind CSS for production; pass `dev` for watch mode |
